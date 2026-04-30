import os
from notion_client import Client
from dotenv import load_dotenv
from src.models import RequirementsDoc

load_dotenv()

def _text_block(content: str) -> dict:
    """Create a Notion paragraph block."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": content}}]
        }
    }

def _heading_block(content: str, level: int = 2) -> dict:
    """Create a Notion heading block."""
    heading_type = f"heading_{level}"
    return {
        "object": "block",
        "type": heading_type,
        heading_type: {
            "rich_text": [{"type": "text", "text": {"content": content}}]
        }
    }

def get_notion_client() -> Client:
    """Return an authenticated Notion client."""
    return Client(auth=os.getenv("NOTION_TOKEN"))

def _extract_text_from_block(block: dict) -> str:
    """Extract plain text from a Notion block."""
    block_type = block.get("type")
    if not block_type:
        return ""

    block_data = block.get(block_type, {})
    rich_text = block_data.get("rich_text", [])

    if rich_text:
        return "".join([t.get("plain_text", "") for t in rich_text])

    # handle table rows
    if block_type == "table_row":
        cells = block_data.get("cells", [])
        return " | ".join(
            "".join([t.get("plain_text", "") for t in cell])
            for cell in cells
        )

    return ""

def _get_block_children(notion: Client, block_id: str) -> list:
    """Recursively get all children of a block."""
    children = []
    cursor = None

    while True:
        if cursor:
            response = notion.blocks.children.list(
                block_id=block_id,
                start_cursor=cursor
            )
        else:
            response = notion.blocks.children.list(block_id=block_id)

        children.extend(response.get("results", []))

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    # recursively get children of children
    all_blocks = []
    for block in children:
        all_blocks.append(block)
        if block.get("has_children"):
            all_blocks.extend(_get_block_children(notion, block["id"]))

    return all_blocks

def list_notion_pages() -> list[dict]:
    """List all pages accessible to the integration."""
    notion = get_notion_client()
    response = notion.search(filter={"property": "object", "value": "page"})
    pages = []
    for page in response.get("results", []):
        title = ""
        title_prop = page.get("properties", {}).get("title", {})
        if title_prop:
            rich_text = title_prop.get("title", [])
            if rich_text:
                title = rich_text[0].get("plain_text", "Untitled")
        pages.append({
            "id": page["id"],
            "title": title,
            "url": page.get("url", "")
        })
    return pages

def read_requirements_from_notion(page_id: str) -> RequirementsDoc:
    """Read a requirements document from Notion and return a RequirementsDoc."""
    notion = get_notion_client()

    # get page metadata
    page = notion.pages.retrieve(page_id=page_id)
    title_prop = page.get("properties", {}).get("title", {})
    title = ""
    if title_prop:
        rich_text = title_prop.get("title", [])
        if rich_text:
            title = rich_text[0].get("plain_text", "Untitled")

    # get all blocks
    blocks = _get_block_children(notion, page_id)

    # extract all text
    raw_lines = []
    current_section = None
    sections = {
        "functional": [],
        "hardware": [],
        "electronics": [],
        "software_firmware": [],
        "performance": [],
        "constraints": []
    }

    section_keywords = {
        "functional": ["functional"],
        "hardware": ["hardware"],
        "electronics": ["electronics"],
        "software": ["software", "firmware"],
        "performance": ["performance"],
        "constraints": ["constraint"]
    }

    for block in blocks:
        text = _extract_text_from_block(block)
        if not text.strip():
            continue

        raw_lines.append(text)
        text_lower = text.lower()

        # detect section headings
        block_type = block.get("type", "")
        if "heading" in block_type:
            current_section = None
            for section, keywords in section_keywords.items():
                if any(kw in text_lower for kw in keywords):
                    current_section = section
                    break

        # add to section if we're in one
        elif current_section and text.strip():
            if current_section == "software":
                sections["software_firmware"].append(text.strip())
            elif current_section in sections:
                sections[current_section].append(text.strip())

    # extract device info from raw content
    raw_content = "\n".join(raw_lines)
    device_name = title.replace(" — Requirements Document", "").replace(" Requirements", "").strip()

    return RequirementsDoc(
        title=title,
        device_name=device_name,
        device_description=_extract_field(raw_content, "Description"),
        target_users=_extract_field(raw_content, "Target Users"),
        raw_content=raw_content,
        functional=sections["functional"],
        hardware=sections["hardware"],
        electronics=sections["electronics"],
        software_firmware=sections["software_firmware"],
        performance=sections["performance"],
        constraints=sections["constraints"]
    )

def _extract_field(content: str, field_name: str) -> str:
    """Extract a field value from raw content."""
    for line in content.split("\n"):
        if field_name.lower() in line.lower() and ":" in line:
            return line.split(":", 1)[1].strip()
    return ""


def write_firmware_docs_to_notion(project, markdown: str) -> str | None:
    """Write firmware documentation to Notion."""
    notion = get_notion_client()
    parent_page_id = os.getenv("NOTION_PAGE_ID")

    try:
        new_page = notion.pages.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            properties={
                "title": {
                    "title": [{"type": "text", "text": {
                        "content": f"{project.name} v{project.version} — Firmware Docs"
                    }}]
                }
            }
        )
        page_id = new_page["id"]
        blocks = []

        for line in markdown.split("\n"):
            if line.startswith("## "):
                blocks.append(_heading_block(line[3:], level=2))
            elif line.startswith("### "):
                blocks.append(_heading_block(line[4:], level=3))
            elif line.startswith("# "):
                blocks.append(_heading_block(line[2:], level=1))
            elif line.strip():
                blocks.append(_text_block(line))

        # chunk into 100 block batches
        chunk_size = 100
        for i in range(0, len(blocks), chunk_size):
            notion.blocks.children.append(
                block_id=page_id,
                children=blocks[i:i + chunk_size]
            )

        return new_page["url"]

    except Exception as e:
        print(f"  ❌ Notion error: {str(e)}")
        return None