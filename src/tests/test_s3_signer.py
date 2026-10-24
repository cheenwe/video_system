"""S3 预签名 URL 测试。

签名实现（SigV4）容易在细节上出错：寻址风格与 canonical URI 不一致、
payload hash 用错、query 没排序——任何一种都会让 OSS 返回
SignatureDoesNotMatch，而本地毫无征兆。

因此除结构性断言外，还提供与 botocore（真实实现）的交叉验证；
环境里没有 botocore 时自动跳过，不影响其余测试。
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from src.core.s3_signer import S3Config, presign_get

KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
AKID = "AKIAIOSFODNN7EXAMPLE"
WHEN = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


def _cfg(**kw) -> S3Config:
    base = dict(
        endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        bucket="mybucket",
        region="cn-hangzhou",
        access_key_id=AKID,
        secret_access_key=KEY,
    )
    base.update(kw)
    return S3Config(**base)


def test_presign_contains_required_query_params():
    url = presign_get(_cfg(), "hls/1/seg_000.ts", expires_in=300, now=WHEN)
    q = parse_qs(urlparse(url).query)
    assert q["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert q["X-Amz-Expires"] == ["300"]
    assert q["X-Amz-SignedHeaders"] == ["host"]
    assert q["X-Amz-Date"] == ["20261025T120000Z"]
    assert AKID in q["X-Amz-Credential"][0]
    assert "cn-hangzhou" in q["X-Amz-Credential"][0]
    assert len(q["X-Amz-Signature"][0]) == 64


def test_presign_virtual_hosted_puts_bucket_in_host():
    """虚拟主机式：bucket 在 host，路径只有 key——与签名口径一致。"""
    url = presign_get(_cfg(), "hls/1/seg_000.ts", expires_in=60, now=WHEN)
    assert url.startswith("https://mybucket.oss-cn-hangzhou.aliyuncs.com/hls/1/seg_000.ts?")


def test_presign_path_style_puts_bucket_in_path():
    cfg = _cfg(endpoint="http://minio.local:9000", path_style=True)
    url = presign_get(cfg, "hls/1/seg_000.ts", expires_in=60, now=WHEN)
    assert url.startswith("http://minio.local:9000/mybucket/hls/1/seg_000.ts?")


def test_presign_cdn_base_url_preferred():
    cfg = _cfg(cdn_base_url="https://cdn.example.com/")
    url = presign_get(cfg, "hls/1/seg_000.ts", expires_in=60, now=WHEN)
    assert url.startswith("https://cdn.example.com/hls/1/seg_000.ts?")
    # CDN 只替换基址，签名仍按 endpoint 计算（region 不变）
    assert "cn-hangzhou" in url


def test_signature_is_deterministic_and_sensitive():
    a = presign_get(_cfg(), "k", expires_in=60, now=WHEN)
    b = presign_get(_cfg(), "k", expires_in=60, now=WHEN)
    assert a == b
    # 任一输入变化签名都必须变
    assert presign_get(_cfg(), "k2", expires_in=60, now=WHEN) != a
    assert presign_get(_cfg(), "k", expires_in=61, now=WHEN) != a
    assert presign_get(_cfg(), "k", expires_in=60, now=WHEN.replace(hour=13)) != a
    assert presign_get(_cfg(region="us-east-1"), "k", expires_in=60, now=WHEN) != a
    assert presign_get(_cfg(secret_access_key="other"), "k", expires_in=60, now=WHEN) != a


def test_key_is_url_encoded_but_slashes_kept():
    url = presign_get(_cfg(), "hls/1/a b+c.mp4", expires_in=60, now=WHEN)
    path = urlparse(url).path
    # 空格必须编码；"+" 也要编码，否则在 query/path 里会被当成空格
    assert path == "/hls/1/a%20b%2Bc.mp4"
    assert "hls/1/" in path  # 层级分隔符保留


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        presign_get(_cfg(bucket=""), "k", expires_in=60, now=WHEN)
    with pytest.raises(ValueError):
        presign_get(_cfg(access_key_id=""), "k", expires_in=60, now=WHEN)
    with pytest.raises(ValueError):
        presign_get(_cfg(), "k", expires_in=0, now=WHEN)


# ---------- 与 botocore 交叉验证（无 botocore 则跳过） ----------

try:  # pragma: no cover - 取决于环境
    import botocore.session  # type: ignore
    from botocore.client import Config  # type: ignore

    _HAS_BOTOCORE = True
except Exception:  # pragma: no cover
    _HAS_BOTOCORE = False


@pytest.mark.skipif(not _HAS_BOTOCORE, reason="未安装 botocore，跳过交叉验证")
@pytest.mark.parametrize(
    "endpoint,bucket,key,expires,path_style",
    [
        ("https://s3.us-east-1.amazonaws.com", "examplebucket", "test.txt", 86400, False),
        ("https://s3.us-east-1.amazonaws.com", "examplebucket", "a/b/c/seg_000.ts", 300, True),
        ("https://oss-cn-hangzhou.aliyuncs.com", "mybucket", "hls/1/init.mp4", 120, False),
        ("http://minio.local:9000", "b", "x/seg_001.m4s", 60, True),
    ],
)
def test_matches_botocore_reference_implementation(
    endpoint, bucket, key, expires, path_style, monkeypatch
):
    """与 botocore 生成的预签名 URL 逐字符一致。

    botocore 用当前时刻签名，因此先取它 URL 里的 X-Amz-Date，
    再用同一时刻调用我们的实现，保证可比。
    """
    import os

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", AKID)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", KEY)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    client = botocore.session.get_session().create_client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if path_style else "virtual"},
        ),
    )
    ref = client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires
    )
    when = datetime.strptime(
        parse_qs(urlparse(ref).query)["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ"
    ).replace(tzinfo=timezone.utc)

    mine = presign_get(
        S3Config(
            endpoint=endpoint,
            bucket=bucket,
            region="us-east-1",
            access_key_id=AKID,
            secret_access_key=KEY,
            path_style=path_style,
        ),
        key,
        expires_in=expires,
        now=when,
    )
    assert mine == ref
