import os
import requests
from dotenv import load_dotenv
from src.models import FirmwareProject

load_dotenv()

NEXUS_URL = os.getenv("NEXUS_URL", "http://10.0.0.221:8081")
NEXUS_USER = os.getenv("NEXUS_USER", "firmware-agent")
NEXUS_PASSWORD = os.getenv("NEXUS_PASSWORD", "")
NEXUS_RAW_REPO = os.getenv("NEXUS_RAW_REPO", "firmware-artifacts")

def _get_auth() -> tuple[str, str]:
    """Return Nexus authentication tuple."""
    return (NEXUS_USER, NEXUS_PASSWORD)

def _get_artifact_path(project: FirmwareProject, filename: str) -> str:
    """Generate the artifact path in Nexus."""
    vendor = project.platform.vendor.lower() if project.platform else "unknown"
    mcu = project.platform.mcu.lower() if project.platform else "unknown"
    return f"{vendor}/{mcu}/{project.name}/{project.version}/{filename}"

def upload_binary(project: FirmwareProject) -> str | None:
    """Upload the .bin file to Nexus."""
    if not project.bin_path or not os.path.exists(project.bin_path):
        print("  ❌ No .bin file found to upload")
        return None

    filename = os.path.basename(project.bin_path)
    artifact_path = _get_artifact_path(project, filename)
    upload_url = f"{NEXUS_URL}/repository/{NEXUS_RAW_REPO}/{artifact_path}"

    print(f"\n📤 Uploading binary to Nexus...")
    print(f"   File: {filename}")
    print(f"   Path: {artifact_path}")

    with open(project.bin_path, "rb") as f:
        response = requests.put(
            upload_url,
            data=f,
            auth=_get_auth(),
            headers={"Content-Type": "application/octet-stream"}
        )

    if response.status_code in [200, 201, 204]:
        print(f"  ✅ Binary uploaded: {upload_url}")
        project.nexus_artifact_url = upload_url
        return upload_url
    else:
        print(f"  ❌ Upload failed: {response.status_code} {response.text}")
        return None

def upload_hex(project: FirmwareProject) -> str | None:
    """Upload the .hex file to Nexus."""
    if not project.hex_path or not os.path.exists(project.hex_path):
        print("  ℹ️ No .hex file found — skipping")
        return None

    filename = os.path.basename(project.hex_path)
    artifact_path = _get_artifact_path(project, filename)
    upload_url = f"{NEXUS_URL}/repository/{NEXUS_RAW_REPO}/{artifact_path}"

    print(f"\n📤 Uploading hex to Nexus...")
    print(f"   File: {filename}")

    with open(project.hex_path, "rb") as f:
        response = requests.put(
            upload_url,
            data=f,
            auth=_get_auth(),
            headers={"Content-Type": "application/octet-stream"}
        )

    if response.status_code in [200, 201, 204]:
        print(f"  ✅ Hex uploaded: {upload_url}")
        return upload_url
    else:
        print(f"  ❌ Hex upload failed: {response.status_code}")
        return None

def upload_build_log(project: FirmwareProject) -> str | None:
    """Upload the build log to Nexus."""
    if not project.build_log:
        return None

    artifact_path = _get_artifact_path(project, "build.log")
    upload_url = f"{NEXUS_URL}/repository/{NEXUS_RAW_REPO}/{artifact_path}"

    print(f"\n📤 Uploading build log to Nexus...")

    response = requests.put(
        upload_url,
        data=project.build_log.encode("utf-8"),
        auth=_get_auth(),
        headers={"Content-Type": "text/plain"}
    )

    if response.status_code in [200, 201, 204]:
        print(f"  ✅ Build log uploaded: {upload_url}")
        return upload_url
    else:
        print(f"  ❌ Build log upload failed: {response.status_code}")
        return None

def list_artifacts(vendor: str = None, mcu: str = None) -> list[dict]:
    """List artifacts in Nexus repository."""
    url = f"{NEXUS_URL}/service/rest/v1/components"
    params = {"repository": NEXUS_RAW_REPO}

    response = requests.get(url, auth=_get_auth(), params=params)

    if response.status_code == 200:
        components = response.json().get("items", [])
        if vendor:
            components = [c for c in components if vendor.lower() in c.get("name", "").lower()]
        if mcu:
            components = [c for c in components if mcu.lower() in c.get("name", "").lower()]
        return components
    else:
        print(f"  ❌ Failed to list artifacts: {response.status_code}")
        return []

def upload_all_artifacts(project: FirmwareProject) -> dict:
    """Upload all build artifacts to Nexus."""
    print(f"\n🗄️ Uploading artifacts to Nexus...")
    results = {
        "bin": upload_binary(project),
        "hex": upload_hex(project),
        "log": upload_build_log(project)
    }

    successful = sum(1 for v in results.values() if v)
    print(f"\n  📊 Uploaded {successful}/{len(results)} artifacts")
    return results