import json
import os
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from dotenv import load_dotenv
from src.prompts import SYSTEM_PROMPT, WELCOME_MESSAGE, COMPLETION_PROMPT
from src.models import FirmwareProject
from src.tools.notion import list_notion_pages, read_requirements_from_notion
from src.tools.codegen import (
    extract_json_from_response,
    parse_firmware_json,
    save_project_to_disk,
    generate_documentation
)
from src.tools.compiler import compile_project
from src.tools.git import init_and_push
from src.tools.nexus import upload_all_artifacts

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY")
)

DONE_KEYWORDS = [
    "generate the firmware",
    "generate firmware",
    "generate the code",
    "generate code",
    "start generating",
    "ready to generate"
]

def is_done(user_input: str) -> bool:
    """Check if the engineer wants to generate firmware."""
    return any(keyword in user_input.lower() for keyword in DONE_KEYWORDS)

def select_requirements_from_notion() -> str | None:
    """Let the engineer select a requirements page from Notion."""
    print("\n📋 Fetching requirements documents from Notion...\n")
    
    try:
        pages = list_notion_pages()
        if not pages:
            print("  ❌ No pages found in Notion")
            return None

        # filter for requirements pages
        req_pages = [p for p in pages if "requirement" in p["title"].lower()]
        
        if not req_pages:
            req_pages = pages  # show all if no requirements pages found

        print("Available requirements documents:")
        for i, page in enumerate(req_pages, 1):
            print(f"  {i}. {page['title']}")
            print(f"     {page['url']}")

        print()
        choice = input("Select a document (number) or press Enter to skip: ").strip()

        if choice and choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(req_pages):
                return req_pages[idx]["id"]

    except Exception as e:
        print(f"  ❌ Error fetching Notion pages: {str(e)}")

    return None

def load_requirements_context(page_id: str) -> str:
    """Load requirements from Notion and format as context."""
    print(f"\n📖 Reading requirements from Notion...")

    try:
        doc = read_requirements_from_notion(page_id)
        print(f"  ✅ Loaded: {doc.title}")

        context = f"""I have loaded the following requirements document from Notion:

Device: {doc.device_name}
Description: {doc.device_description}
Target Users: {doc.target_users}

Requirements Summary:
- Functional requirements: {len(doc.functional)} items
- Hardware requirements: {len(doc.hardware)} items  
- Electronics requirements: {len(doc.electronics)} items
- Software/Firmware requirements: {len(doc.software_firmware)} items
- Performance requirements: {len(doc.performance)} items
- Constraints: {len(doc.constraints)} items

Full requirements:
{doc.raw_content[:3000]}

Based on these requirements, let's discuss the firmware architecture and platform selection.
What platform are we targeting for this device?"""

        return context

    except Exception as e:
        print(f"  ❌ Error reading requirements: {str(e)}")
        return ""

def generate_and_deploy(messages: list) -> FirmwareProject | None:
    """Extract requirements from conversation and generate, build, deploy firmware."""
    print("\n⚙️  Generating firmware...\n")

    # ask LLM to generate firmware JSON
    extraction_messages = messages + [
        HumanMessage(content=COMPLETION_PROMPT)
    ]

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = llm.invoke(extraction_messages)
            json_str = extract_json_from_response(response.content)

            if not json_str:
                print(f"  ⚠️ No JSON found in response (attempt {attempt + 1}/{max_retries})")
                continue

            # parse into firmware project
            project = parse_firmware_json(json_str)

            # debug — print what was parsed
            print(f"\n🔍 Debug — parsed project:")
            print(f"  main_c length: {len(project.main_c)}")
            print(f"  cmakelists length: {len(project.cmakelists)}")
            print(f"  platformio_ini length: {len(project.platformio_ini)}")
            print(f"  modules: {[(m.name, len(m.code)) for m in project.modules]}")
            print(f"  files from LLM: {list(json.loads(json_str).get('files', {}).keys())}")
            print(f"  raw json keys: {list(json.loads(json_str).keys())}")

            print(f"  ✅ Firmware project parsed: {project.name}")
            print(f"  📦 Platform: {project.platform.name}")
            print(f"  🔧 Toolchain: {project.platform.toolchain}")

            # save to disk
            print(f"\n💾 Saving project files...")
            project_dir = save_project_to_disk(project, output_dir="output")
            print(f"  ✅ Saved to: {project_dir}")

            # compile
            print(f"\n🔨 Compiling firmware...")
            success, build_log = compile_project(project, project_dir)

            if success:
                print(f"  ✅ Compilation successful!")
            else:
                print(f"  ⚠️ Compilation failed — continuing with source code only")

            # push to github
            print(f"\n📤 Pushing to GitHub...")
            git_url = init_and_push(project, project_dir)
            if git_url:
                print(f"  ✅ Source code: {git_url}")

            # upload artifacts to nexus
            if success:
                upload_all_artifacts(project)

            # generate documentation
            print(f"\n📝 Generating documentation...")
            doc_markdown = generate_documentation(project)

            # write to notion
            try:
                from src.tools.notion import write_firmware_docs_to_notion
                notion_url = write_firmware_docs_to_notion(project, doc_markdown)
                if notion_url:
                    project.notion_doc_url = notion_url
                    print(f"  ✅ Documentation: {notion_url}")
            except Exception as e:
                print(f"  ⚠️ Notion documentation failed: {str(e)}")

            return project

        except Exception as e:
            print(f"  ❌ Error on attempt {attempt + 1}: {str(e)}")
            if attempt == max_retries - 1:
                print("  ❌ All attempts failed")
                return None

    return None

def print_summary(project: FirmwareProject):
    """Print a final summary of the generated firmware."""
    print("\n" + "=" * 50)
    print("  ✅ FIRMWARE GENERATION COMPLETE")
    print("=" * 50)
    print(project.summary())
    print("=" * 50)

def run_agent():
    """Run the firmware agent."""
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    print(f"\n🤖 {WELCOME_MESSAGE}\n")

    # ask if they want to load from notion
    choice = input("You: ").strip()
    messages.append(HumanMessage(content=choice))

    # if they want notion requirements
    if any(word in choice.lower() for word in ["notion", "requirements", "1", "read", "load"]):
        page_id = select_requirements_from_notion()
        if page_id:
            context = load_requirements_context(page_id)
            if context:
                messages.append(HumanMessage(content=context))
                response = llm.invoke(messages)
                messages.append(AIMessage(content=response.content))
                print(f"\n🤖 {response.content}\n")

    # main conversation loop
    while True:
        user_input = input("You: ").strip()

        if not user_input:
            continue

        if user_input.lower() in ["quit", "exit"]:
            print("\n👋 Goodbye!")
            break

        if is_done(user_input):
            project = generate_and_deploy(messages)
            if project:
                print_summary(project)
            break

        # normal conversation turn
        messages.append(HumanMessage(content=user_input))

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                response = llm.invoke(messages)
                content = response.content

                # strip any premature JSON
                if "```json" in content:
                    content = content[:content.find("```json")].strip()

                messages.append(AIMessage(content=content))
                print(f"\n🤖 {content}\n")
                break

            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"❌ Error: {str(e)}")
                else:
                    print(f"⚠️ Retrying ({retry_count}/{max_retries})...")