"""S3 兼容对象存储的预签名 URL（纯 Python，无 boto3 依赖）。

用于把 HLS 分片的字节下发/上传转移到 OSS/CDN：平台仍负责鉴权，鉴权通过后
把一个短时效的预签名 URL 交给客户端或上传线程。支持任何 S3 兼容服务
（阿里云 OSS 的 S3 兼容入口、MinIO、腾讯云 COS 的 S3 兼容端点等）。

两种寻址风格必须与 canonical URI 保持一致，否则签名必然对不上：
- 虚拟主机式（默认）：host=<bucket>.<endpoint>，路径=/{key}
- 路径式：host=<endpoint>，路径=/{bucket}/{key}（部分 MinIO/自建只支持这种）

payload hash 统一用 `UNSIGNED-PAYLOAD`（S3 对 HTTPS 上的预签名请求允许），
与 botocore 的行为一致；用空串哈希会导致 SignatureDoesNotMatch。
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

_UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"


@dataclass(frozen=True)
class S3Config:
    endpoint: str  # 例如 https://oss-cn-hangzhou.aliyuncs.com
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str
    # 可选 CDN/自定义域名；配置后优先用它（签名仍按 endpoint 计算）
    cdn_base_url: str = ""
    # 路径式寻址；默认虚拟主机式
    path_style: bool = False

    def normalized_endpoint(self) -> str:
        return self.endpoint.strip().rstrip("/")

    def _endpoint_host(self) -> str:
        raw = self.normalized_endpoint()
        if "://" in raw:
            raw = raw.split("://", 1)[1]
        return raw.rstrip("/")

    def host_for_signing(self) -> str:
        if self.path_style:
            return self._endpoint_host()
        return f"{self.bucket}.{self._endpoint_host()}"

    def canonical_uri(self, key: str) -> str:
        k = quote(key.lstrip("/"), safe="/-_.~")
        if self.path_style:
            return f"/{self.bucket}/{k}"
        return f"/{k}"

    def _scheme(self) -> str:
        endpoint = self.normalized_endpoint()
        if "://" in endpoint:
            return endpoint.split("://", 1)[0]
        return "https"


def presign(
    cfg: S3Config,
    method: str,
    key: str,
    *,
    expires_in: int = 300,
    now: datetime | None = None,
) -> str:
    """生成任意方法的预签名 URL（SigV4 query 参数形式，只签 host 头）。"""
    if not cfg.bucket or not cfg.access_key_id or not cfg.secret_access_key:
        raise ValueError("S3 配置不完整（bucket/access_key/secret 必填）")
    if expires_in <= 0:
        raise ValueError("expires_in 必须为正数")

    now = now or datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    region = cfg.region or "us-east-1"
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"

    query = {
        "X-Amz-Algorithm": algorithm,
        "X-Amz-Credential": f"{cfg.access_key_id}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(int(expires_in)),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = urlencode(sorted(query.items()), quote_via=quote, safe="-_.~")
    canonical_request = "\n".join(
        [
            method.upper(),
            cfg.canonical_uri(key),
            canonical_query,
            f"host:{cfg.host_for_signing()}\n",
            "host",
            _UNSIGNED_PAYLOAD,
        ]
    )
    string_to_sign = "\n".join(
        [
            algorithm,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(cfg.secret_access_key, date_stamp, region, "s3"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    signed_query = f"{canonical_query}&X-Amz-Signature={signature}"
    url_key = quote(key.lstrip("/"), safe="/-_.~")
    if cfg.path_style:
        return f"{cfg._scheme()}://{cfg.host_for_signing()}/{cfg.bucket}/{url_key}?{signed_query}"
    base = cfg.cdn_base_url.strip().rstrip("/") if cfg.cdn_base_url else ""
    if base:
        return f"{base}/{url_key}?{signed_query}"
    return f"{cfg._scheme()}://{cfg.host_for_signing()}/{url_key}?{signed_query}"


def presign_get(
    cfg: S3Config,
    key: str,
    *,
    expires_in: int = 300,
    now: datetime | None = None,
) -> str:
    """GET 预签名（播放场景）。"""
    return presign(cfg, "GET", key, expires_in=expires_in, now=now)


def presign_put(
    cfg: S3Config,
    key: str,
    *,
    expires_in: int = 900,
    now: datetime | None = None,
) -> str:
    """PUT 预签名（上传场景）。

    调用方必须带 `x-amz-content-sha256: UNSIGNED-PAYLOAD` 请求头，
    与签名时的 payload hash 保持一致。
    """
    return presign(cfg, "PUT", key, expires_in=expires_in, now=now)


def _signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, "aws4_request")


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
