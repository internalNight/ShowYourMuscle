"""Audit the shipped package: what the release artifact contains and what it is allowed to do.

This is the evidence behind the app's data-handling claims. It reads a built debug APK and the current
web build and records four groups of facts:

* the archive itself (bytes, SHA-256, entry count, compressed payload, packaged index size, cache
  marker, which card sentences are inside it);
* the Android manifest as the packaging tool reports it (package, SDK range, label, launchable
  activity, debuggable flag, and the exact permission list with a written reason for each);
* the code's network and bridge surface (every fetch, XMLHttpRequest, WebSocket, beacon, share call),
  every external host inside the packaged page, and every local-storage key the app writes;
* the limitations of a static audit, so no reader mistakes it for a runtime guarantee.

Run as: .cache/opensim-venv/Scripts/python.exe scripts/audit_shipped_package.py [--apk PATH]
The report is written to docs/data/shipped_package_audit.json and is guarded by
scripts/check-shipped-package-audit.mjs.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/data/shipped_package_audit.json"
RELEASES = ROOT / "releases"
DIST_INDEX = ROOT / "dist/index.html"
SW = ROOT / "public/sw.js"
SOURCE_MANIFEST = ROOT / "android/app/src/main/AndroidManifest.xml"
ANDROID_DOC = ROOT / "docs/安卓构建.md"

SDK_CANDIDATES = [Path(r"D:\Android\Sdk")] + [
    Path(value) for value in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"))
    if value]
JDK_CANDIDATES = [Path(r"D:\Android\jdk-21.0.12.1+1")] + [
    Path(value) for value in (os.environ.get("JAVA_HOME"),) if value]

# Every network or bridge call in src/, classified once by hand. A new or edited call no longer matches
# a key here, so the check fails until someone reviews what the app can talk to.
CLASSIFIED_SINKS = {
    "'/data/squat_opensim_reference.json'":
        ("local asset", "same-origin packaged JSON; the APK holds it, so no host is contacted"),
    "Share.share(":
        ("native bridge", "Capacitor share sheet; only runs when the user taps export, sends a file the "
                          "user chose to save"),
    "navigator.share(":
        ("web share", "browser share sheet; the same user-initiated export path on the web build"),
}
UNREVIEWED = "unreviewed"

# Every external host that may appear inside the packaged page, classified the same way.
EXTERNAL_HOSTS = {
    "creativecommons.org": "licence text",
    "csr.bu.edu": "cited data source",
    "doi.org": "citation link",
    "e-kjab.org": "citation link",
    "figshare.com": "cited data source",
    "github.com": "cited model source",
    "huggingface.co": "cited dataset source",
    "humandatacorpus.org": "cited data source",
    "jcgt.org": "citation link",
    "pmc.ncbi.nlm.nih.gov": "citation link",
    "www.nature.com": "citation link",
    "www.w3.org": "XML namespace string, not a request",
    "zenodo.org": "cited data source",
}

# Every local-storage key the app writes, what it holds, and whether it leaves the device.
STORAGE_KEYS = {
    "muscle-atlas-profile-v1": ("身体参数（身高、体重、体脂与围度）", "只有用户主动导出备份时才会写出"),
    "muscle-atlas-training-v1": ("训练记录", "只有用户主动导出备份时才会写出"),
    "muscle-atlas-exercise-v1": ("当前动作", "不导出"),
    "muscle-atlas-loads-v1": ("三个动作的当前杠铃重量", "不导出"),
    "muscle-atlas-squat-bar-offset-cm-v1": ("深蹲杠铃位置", "不导出"),
    "muscle-atlas-squat-depth-deg-v1": ("深蹲模型幅度", "不导出"),
    "muscle-atlas-cycle-duration-s-v1": ("动作周期", "不导出"),
    "muscle-atlas-bench-tempo-v1": ("卧推节奏", "不导出"),
}

PERMISSION_REASONS = {
    "android.permission.INTERNET":
        "Capacitor 的 WebView 通过本机 HTTP 服务加载打包资源；应用本身只请求同源打包文件，"
        "代码里没有任何第三方接口",
    "DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION":
        "AndroidX 库自己声明的私有权限，用来限制动态注册的广播接收器只在本应用内可见；"
        "不是系统的敏感权限",
}

CARD_TOKENS = ["八块肌肉", "不穿模", "7.6 mm", "97／101", "20 对网格相交", "28.8 mm",
               "87 帧降到 5 帧", "73 帧降到 0 帧", "67 帧里相接", "2.6–3.7 cm", "81／97",
               "靠关节间隙修不了", "四种常数方案", "173 降到 86 帧", "365 mm", "没有采纳",
               "71 帧降到 52 帧", "复合的螺旋运动", "关节软骨"]
SINK_PATTERN = re.compile(r"\b(fetch\s*\(|new\s+XMLHttpRequest|new\s+WebSocket|sendBeacon|"
                          r"new\s+EventSource|CapacitorHttp|axios|navigator\.share\s*\(|Share\.share\s*\()")
STORAGE_PATTERN = re.compile(r"localStorage\.(?:setItem|getItem|removeItem)\(\s*['\"`]([^'\"`]+)")
HOST_PATTERN = re.compile(r"https?://([A-Za-z0-9._-]+)")


def newest_apk():
    candidates = sorted(RELEASES.glob("muscle-atlas-debug-v*.apk"),
                        key=lambda path: int(re.search(r"v(\d+)", path.stem).group(1)))
    if not candidates:
        raise SystemExit("no release APK found in releases/")
    return candidates[-1]


def find_tool(name, roots, relative):
    for root in roots:
        if not root or not str(root):
            continue
        candidate = Path(root) / relative
        if candidate.exists():
            return candidate
    return None


def run(command, env=None):
    try:
        completed = subprocess.run([str(part) for part in command], capture_output=True, env=env)
    except OSError as error:
        return None, str(error)
    text = completed.stdout.decode("utf-8", "replace") + completed.stderr.decode("utf-8", "replace")
    if completed.returncode != 0:
        return None, text.strip() or f"exit {completed.returncode}"
    return text, None


def manifest_facts(apk):
    aapt2 = find_tool("aapt2", SDK_CANDIDATES, "build-tools/35.0.0/aapt2.exe")
    if aapt2 is None:
        return {"status": "unavailable", "reason": "aapt2 not found under the Android SDK"}
    text, error = run([aapt2, "dump", "badging", apk])
    if text is None:
        return {"status": "unavailable", "reason": error}

    def field(pattern, default=None):
        match = re.search(pattern, text)
        return match.group(1) if match else default

    package = field(r"package: name='([^']+)'")
    permissions = []
    for name in re.findall(r"uses-permission: name='([^']+)'", text):
        reasons = [reason for marker, reason in PERMISSION_REASONS.items() if marker in name]
        permissions.append({"name": name,
                            "reason": reasons[0] if reasons else UNREVIEWED,
                            "platformPermission": not name.startswith(package or "\0")})
    label = field(r"application-label:'([^']+)'", "")
    launchable = re.search(r"launchable-activity: name='([^']+)'", text)
    locales = re.search(r"locales: (.+)", text)
    return {
        "status": "measured",
        "tool": str(aapt2),
        "packageName": package,
        "versionCode": int(field(r"versionCode='(\d+)'", "0")),
        "versionName": field(r"versionName='([^']*)'", ""),
        "minSdkVersion": int(field(r"minSdkVersion:'(\d+)'", "0")),
        "targetSdkVersion": int(field(r"targetSdkVersion:'(\d+)'", "0")),
        "compileSdkVersion": int(field(r"compileSdkVersion='(\d+)'", "0")),
        "applicationLabel": label,
        "launchableActivity": launchable.group(1) if launchable else None,
        "debuggable": "application-debuggable" in text,
        "permissions": permissions,
        "nativeCode": sorted(set(re.findall(r"native-code: (.+)", text))),
        "supportsAnyDensity": "supports-any-density: 'true'" in text,
        "localeCount": len(re.findall(r"'[a-zA-Z_-]+'", locales.group(1))) if locales else 0,
        "impliedFeatures": re.findall(r"uses-implied-feature: name='([^']+)'", text),
    }


def signing_facts(apk):
    apksigner = find_tool("apksigner", SDK_CANDIDATES, "build-tools/35.0.0/apksigner.bat")
    if apksigner is None:
        return {"status": "unavailable", "reason": "apksigner not found under the Android SDK"}
    jdk = next((path for path in JDK_CANDIDATES if path and path.exists()), None)
    if jdk is None:
        return {"status": "unavailable", "reason": "no JDK with bin/java.exe found for apksigner"}
    env = dict(os.environ, JAVA_HOME=str(jdk))
    text, error = run([apksigner, "verify", "--print-certs", apk], env=env)
    if text is None:
        return {"status": "unavailable", "reason": error.splitlines()[0] if error else "apksigner failed"}
    subject = re.search(r"Signer #1 certificate DN: (.+)", text)
    digest = re.search(r"Signer #1 certificate SHA-256 digest: ([0-9a-f]+)", text)
    sha1 = re.search(r"Signer #1 certificate SHA-1 digest: ([0-9a-f]+)", text)
    return {"status": "measured", "tool": str(apksigner), "jdk": str(jdk),
            "certificateDn": subject.group(1).strip() if subject else None,
            "certificateSha256": digest.group(1).upper() if digest else None,
            "certificateSha1": sha1.group(1).upper() if sha1 else None,
            "debugCertificate": bool(subject and "Android Debug" in subject.group(1))}


def packaged_manifest_facts(apk):
    """Read the merged manifest as packaged, where library components can add exported entries."""
    aapt2 = find_tool("aapt2", SDK_CANDIDATES, "build-tools/35.0.0/aapt2.exe")
    if aapt2 is None:
        return {"status": "unavailable", "reason": "aapt2 not found under the Android SDK"}
    text, error = run([aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", apk])
    if text is None:
        return {"status": "unavailable", "reason": error}

    def value(name):
        match = re.search(rf"android:{name}\(0x[0-9a-f]+\)=(\S+)", text)
        return match.group(1).strip('"') if match else None

    components = []
    current = None
    for line in text.split("\n"):
        stripped = line.strip()
        element = re.match(r"E: (\w+) \(line=\d+\)", stripped)
        if element:
            if current and current["kind"] in ("activity", "activity-alias", "service", "receiver",
                                               "provider"):
                components.append(current)
            current = {"kind": element.group(1), "name": None, "exported": None, "permission": None}
            continue
        if current is None:
            continue
        name = re.search(r'android:name\(0x[0-9a-f]+\)="([^"]+)"', stripped)
        exported = re.search(r"android:exported\(0x[0-9a-f]+\)=(\S+)", stripped)
        permission = re.search(r'android:permission\(0x[0-9a-f]+\)="([^"]+)"', stripped)
        if name and current["name"] is None:
            current["name"] = name.group(1)
        if exported:
            current["exported"] = exported.group(1).strip('"') == "true"
        if permission:
            current["permission"] = permission.group(1)
    if current and current["kind"] in ("activity", "activity-alias", "service", "receiver", "provider"):
        components.append(current)
    cleartext = value("usesCleartextTraffic")
    return {
        "status": "measured",
        "tool": str(aapt2),
        "debuggable": value("debuggable") == "true",
        "allowBackup": value("allowBackup"),
        "extractNativeLibs": value("extractNativeLibs"),
        "usesCleartextTraffic": cleartext,
        "networkSecurityConfig": value("networkSecurityConfig"),
        "exportedComponents": [item for item in components if item["exported"] is True],
        "declaredComponents": len(components),
        "note": "打包后的清单来自库合并结果，因此比手写清单多出组件；没有 usesCleartextTraffic 时，"
                "targetSdk 36 下明文流量默认关闭，Capacitor 用 https://localhost 加载打包资源。"
                "对外的组件若带 android:permission 保护会一并记录。",
    }


def source_manifest_facts():
    """Read the hand-written manifest, which holds the privacy-relevant flags."""
    if not SOURCE_MANIFEST.exists():
        return {"status": "unavailable", "reason": "no source AndroidManifest.xml"}
    text = SOURCE_MANIFEST.read_text(encoding="utf-8")

    def attribute(name, element=r"application"):
        block = re.search(rf"<{element}\b(.*?)(?:>|/>)", text, re.S)
        if not block:
            return None
        match = re.search(rf'android:{name}="([^"]+)"', block.group(1))
        return match.group(1) if match else None

    return {
        "status": "measured",
        "path": str(SOURCE_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        "allowBackup": attribute("allowBackup"),
        "fullBackupContent": attribute("fullBackupContent"),
        "dataExtractionRules": attribute("dataExtractionRules"),
        "activityExported": attribute("exported", "activity"),
        "activityLaunchMode": attribute("launchMode", "activity"),
        "fileProviderExported": attribute("exported", "provider"),
        "fileProviderGrantUriPermissions": attribute("grantUriPermissions", "provider"),
        "usesCleartextTraffic": attribute("usesCleartextTraffic"),
        "declaredPermissions": re.findall(r'uses-permission android:name="([^"]+)"', text),
        "note": "allowBackup=false 表示系统不会把应用数据自动备份到云端；FileProvider 不对外导出，"
                "只在用户主动导出时按次授权给选中的目标应用",
    }


def source_sinks():
    records = []
    for path in sorted((ROOT / "src").rglob("*.ts")):
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if not SINK_PATTERN.search(line):
                continue
            trimmed = line.strip()
            classification, note = UNREVIEWED, "this call has not been reviewed"
            for marker, (kind, explanation) in CLASSIFIED_SINKS.items():
                if marker in trimmed:
                    classification, note = kind, explanation
                    break
            records.append({"file": str(path.relative_to(ROOT)).replace("\\", "/"), "line": number,
                            "code": trimmed[:160], "classification": classification, "note": note})
    return records


def storage_keys():
    found = {}
    for path in sorted((ROOT / "src").rglob("*.ts")):
        for line in path.read_text(encoding="utf-8").split("\n"):
            for match in STORAGE_PATTERN.finditer(line):
                key = match.group(1)
                contains, leaves = STORAGE_KEYS.get(key, (UNREVIEWED, UNREVIEWED))
                found[key] = {
                    "files": sorted(set(found.get(key, {}).get("files", []) +
                                        [str(path.relative_to(ROOT)).replace("\\", "/")])),
                    "contains": contains,
                    "leavesDevice": leaves,
                }
    return dict(sorted(found.items()))


def external_hosts(text):
    hosts = {}
    for host in sorted(set(HOST_PATTERN.findall(text))):
        hosts[host] = {"classification": EXTERNAL_HOSTS.get(host, UNREVIEWED),
                       "occurrences": text.count(host)}
    return hosts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    apk = args.apk or newest_apk()
    report_path = args.report if args.report.is_absolute() else ROOT / args.report

    raw = apk.read_bytes()
    with zipfile.ZipFile(apk) as archive:
        infos = archive.infolist()
        index_entries = [info for info in infos if info.filename.endswith("assets/public/index.html")]
        if not index_entries:
            raise SystemExit("the APK has no packaged assets/public/index.html")
        index_bytes = archive.read(index_entries[0].filename)
        index_text = index_bytes.decode("utf-8", "replace")
        entry_names = [info.filename for info in infos]
        compressed = sum(info.compress_size for info in infos)

    cache_marker = re.search(r"muscle-atlas-v(\d+)", index_text)
    sw_marker = re.search(r"muscle-atlas-v(\d+)", SW.read_text(encoding="utf-8"))
    dist_text = DIST_INDEX.read_text(encoding="utf-8") if DIST_INDEX.exists() else ""
    doc_text = ANDROID_DOC.read_text(encoding="utf-8")
    doc_bytes = re.search(r"\*\*(\d{1,3}(?:,\d{3})+) 字节\*\*", doc_text)
    doc_sha = re.search(r"SHA-256 `([0-9A-F]{64})`", doc_text)

    report = {
        "status": "static_package_audit_not_runtime_verification",
        "auditedAt": date.today().isoformat(),
        "apk": {
            "path": str(apk.relative_to(ROOT)).replace("\\", "/"),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest().upper(),
        },
        "archive": {
            "entries": len(infos),
            "compressedPayloadBytes": compressed,
            "packedIndexPath": index_entries[0].filename,
            "packedIndexBytes": len(index_bytes),
            "cacheMarker": f"muscle-atlas-v{cache_marker.group(1)}" if cache_marker else None,
            "arm26Entries": sum(1 for name in entry_names if re.search("arm26", name, re.I)),
            "cardTokensPresent": [token for token in CARD_TOKENS if token in index_text],
            "cardTokensMissing": [token for token in CARD_TOKENS if token not in index_text],
        },
        "crossCheck": {
            "androidDocBytesMatch": bool(doc_bytes) and int(doc_bytes.group(1).replace(",", "")) == len(raw),
            "androidDocShaMatch": bool(doc_sha) and doc_sha.group(1) == hashlib.sha256(raw).hexdigest().upper(),
            "serviceWorkerMarker": f"muscle-atlas-v{sw_marker.group(1)}" if sw_marker else None,
            "currentDistMarker": (re.search(r"muscle-atlas-v(\d+)", dist_text).group(0)
                                  if re.search(r"muscle-atlas-v(\d+)", dist_text) else None),
        },
        "manifest": manifest_facts(apk),
        "packagedManifest": packaged_manifest_facts(apk),
        "signing": signing_facts(apk),
        "sourceManifest": source_manifest_facts(),
        "networkSinks": source_sinks(),
        "externalHostsInPackagedPage": external_hosts(index_text),
        "localStorageKeys": storage_keys(),
        "limitations": [
            "静态审计：读的是打包产物与源码调用点，不能证明运行期 WebView 一次都没有打开网络连接",
            "APK 清单来自 aapt2 的输出；若工具缺失，报告会写明 unavailable 而不是猜测",
            "被审计的产物是调试签名包，正式发布前还要重新审计",
            "外部主机只统计打包页面里出现的字符串，不能代替对每条链接目标的内容审查",
            "没有 Android 真机的安装、启动或权限行为验收",
            "localStorage 只列出应用自己写入的键；系统或 WebView 自身的数据不在此列",
            "签名信息来自本机 JDK 下的 apksigner，证书是可公开的调试证书",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    unreviewed_sinks = [item["code"] for item in report["networkSinks"]
                        if item["classification"] == UNREVIEWED]
    unreviewed_hosts = [host for host, item in report["externalHostsInPackagedPage"].items()
                        if item["classification"] == UNREVIEWED]
    print("SHIPPED_PACKAGE_AUDIT",
          json.dumps({"apk": report["apk"]["path"], "bytes": len(raw),
                      "sha256": report["apk"]["sha256"][:12],
                      "cacheMarker": report["archive"]["cacheMarker"],
                      "packedIndexBytes": report["archive"]["packedIndexBytes"],
                      "permissions": [item["name"] for item in report["manifest"].get("permissions", [])]
                      if report["manifest"].get("status") == "measured" else "unavailable",
                      "networkSinks": len(report["networkSinks"]),
                      "unreviewedSinks": unreviewed_sinks,
                      "externalHosts": len(report["externalHostsInPackagedPage"]),
                      "unreviewedHosts": unreviewed_hosts,
                      "storageKeys": len(report["localStorageKeys"]),
                      "docBytesMatch": report["crossCheck"]["androidDocBytesMatch"],
                      "docShaMatch": report["crossCheck"]["androidDocShaMatch"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
