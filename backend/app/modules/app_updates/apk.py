"""Reads what an uploaded APK says about itself: its package name, versionCode and versionName.

An APK is a zip holding AndroidManifest.xml compiled to Android's binary XML (AXML). Only what is needed is read:
the string pool, the resource-id map (attribute names are matched by their framework id, as Android does), and the
attributes of the first element, <manifest>. No aapt, no outside tool. The signature is not checked here: Android
refuses to install an update signed with another key, whatever the server says.
"""

import io
import struct
import zipfile
from dataclasses import dataclass

RES_XML = 0x0003
RES_STRING_POOL = 0x0001
RES_XML_RESOURCE_MAP = 0x0180
RES_XML_START_ELEMENT = 0x0102
UTF8_FLAG = 0x100
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
ATTR_VERSION_CODE = 0x0101021B
ATTR_VERSION_NAME = 0x0101021C
MANIFEST_MAX = 4 * 1024 * 1024


class ApkError(ValueError):
    """Not an APK this server can read (the code says why)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ApkInfo:
    package: str
    version_code: int
    version_name: str | None


def read(data: bytes) -> ApkInfo:
    if not data.startswith(b"PK\x03\x04"):
        raise ApkError("apk_not_zip")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            try:
                entry = z.getinfo("AndroidManifest.xml")
            except KeyError:
                raise ApkError("apk_no_manifest") from None
            if entry.file_size > MANIFEST_MAX:
                raise ApkError("apk_manifest_unreadable")
            manifest = z.read(entry)
    except zipfile.BadZipFile:
        raise ApkError("apk_not_zip") from None
    return parse_manifest(manifest)


def _string(buf: bytes, pool: int, utf8: bool, offset: int) -> str:
    p = pool + offset
    if utf8:
        n = buf[p]
        p += 2 if n & 0x80 else 1  # the length in UTF-16 units, skipped
        n = buf[p]
        if n & 0x80:
            n = ((n & 0x7F) << 8) | buf[p + 1]
            p += 2
        else:
            p += 1
        return buf[p : p + n].decode("utf-8", "replace")
    (n,) = struct.unpack_from("<H", buf, p)
    p += 2
    if n & 0x8000:
        (low,) = struct.unpack_from("<H", buf, p)
        n = ((n & 0x7FFF) << 16) | low
        p += 2
    return buf[p : p + 2 * n].decode("utf-16-le", "replace")


def parse_manifest(buf: bytes) -> ApkInfo:
    try:
        return _parse(buf)
    except (struct.error, IndexError):
        raise ApkError("apk_manifest_unreadable") from None


def _parse(buf: bytes) -> ApkInfo:
    kind, header, _ = struct.unpack_from("<HHI", buf, 0)
    if kind != RES_XML:
        raise ApkError("apk_manifest_unreadable")
    strings: list[str] = []
    ids: list[int] = []
    pos = header
    while pos + 8 <= len(buf):
        kind, header, size = struct.unpack_from("<HHI", buf, pos)
        if size < 8:
            break
        if kind == RES_STRING_POOL:
            count, _, flags, start, _ = struct.unpack_from("<IIIII", buf, pos + 8)
            offsets = struct.unpack_from(f"<{count}I", buf, pos + header)
            utf8 = bool(flags & UTF8_FLAG)
            strings = [_string(buf, pos + start, utf8, o) for o in offsets]
        elif kind == RES_XML_RESOURCE_MAP:
            ids = list(struct.unpack_from(f"<{(size - header) // 4}I", buf, pos + header))
        elif kind == RES_XML_START_ELEMENT:
            _, name, attr_start, attr_size, attr_count = struct.unpack_from("<IIHHH", buf, pos + header)
            if strings[name] != "manifest":
                break
            values: dict[str, object] = {}
            for i in range(attr_count):
                a = pos + header + attr_start + i * attr_size
                _, aname, raw, _, _, dtype, data = struct.unpack_from("<IIIHBBI", buf, a)
                rid = ids[aname] if aname < len(ids) else 0
                key = {ATTR_VERSION_CODE: "versionCode", ATTR_VERSION_NAME: "versionName"}.get(rid) or strings[aname]
                if dtype == TYPE_STRING:
                    values[key] = strings[data]
                elif dtype in (TYPE_INT_DEC, TYPE_INT_HEX):
                    values[key] = data
                elif raw != 0xFFFFFFFF:
                    values[key] = strings[raw]
            package, code, name_ = values.get("package"), values.get("versionCode"), values.get("versionName")
            if isinstance(code, str) and code.isdigit():
                code = int(code)
            if not isinstance(package, str) or not package or not isinstance(code, int) or code <= 0:
                raise ApkError("apk_manifest_unreadable")
            return ApkInfo(package, code, name_ if isinstance(name_, str) else None)
        pos += size
    raise ApkError("apk_manifest_unreadable")


# ------------------------------------------------------------------ a writer, for tests and fixtures


def build_manifest(package: str, version_code: int, version_name: str = "1.0") -> bytes:
    """The smallest binary manifest this reader (and aapt) accepts: <manifest package versionCode versionName>."""
    strs = ["versionCode", "versionName", "package", "manifest", "http://schemas.android.com/apk/res/android",
            "android", version_name, package]  # fmt: skip

    def utf16(s: str) -> bytes:
        return struct.pack("<H", len(s)) + s.encode("utf-16-le") + b"\0\0"

    data = b"".join(utf16(s) for s in strs)
    data += b"\0" * (-len(data) % 4)
    offsets, o = [], 0
    for s in strs:
        offsets.append(o)
        o += 2 + 2 * len(s) + 2
    pool_header = 28
    start = pool_header + 4 * len(strs)
    pool = struct.pack("<HHIIIIII", RES_STRING_POOL, pool_header, start + len(data), len(strs), 0, 0, start, 0)
    pool += struct.pack(f"<{len(strs)}I", *offsets) + data
    resmap = struct.pack("<HHI", RES_XML_RESOURCE_MAP, 8, 16) + struct.pack("<II", ATTR_VERSION_CODE, ATTR_VERSION_NAME)
    ns = 4
    attrs = [
        struct.pack("<IIIHBBI", ns, 0, 0xFFFFFFFF, 8, 0, TYPE_INT_DEC, version_code),
        struct.pack("<IIIHBBI", ns, 1, 6, 8, 0, TYPE_STRING, 6),
        struct.pack("<IIIHBBI", 0xFFFFFFFF, 2, 7, 8, 0, TYPE_STRING, 7),
    ]
    body = struct.pack("<IIHHHHHH", 0xFFFFFFFF, 3, 20, 20, len(attrs), 0, 0, 0) + b"".join(attrs)
    start_ns = struct.pack("<HHIII", 0x0100, 16, 24, 1, 0xFFFFFFFF) + struct.pack("<II", 5, 4)
    element = struct.pack("<HHIII", RES_XML_START_ELEMENT, 16, 16 + len(body), 1, 0xFFFFFFFF) + body
    end = struct.pack("<HHIII", 0x0103, 16, 24, 1, 0xFFFFFFFF) + struct.pack("<II", 0xFFFFFFFF, 3)
    end_ns = struct.pack("<HHIII", 0x0101, 16, 24, 1, 0xFFFFFFFF) + struct.pack("<II", 5, 4)
    chunks = pool + resmap + start_ns + element + end + end_ns
    return struct.pack("<HHI", RES_XML, 8, 8 + len(chunks)) + chunks


def build_apk(package: str, version_code: int, version_name: str = "1.0", *, padding: int = 0) -> bytes:
    """A zip with the manifest above (and some filler): enough for this server, not for a phone."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("AndroidManifest.xml", build_manifest(package, version_code, version_name))
        z.writestr("classes.dex", b"dex\n035\0" + b"\0" * padding)
    return out.getvalue()
