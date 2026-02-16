# NOTION MODULE DEPENDENCY ORCHESTRATOR (NMDO)

import os
import subprocess
import requests
import logging
from dotenv import load_dotenv

# Load credentials
load_dotenv()
NOTION_API_KEY = os.getenv("NOTION_API_KEY_INTEGRATION_NMDO")
SEED_DATABASE_ID = os.getenv("SEED_DATABASE_ID")
MODULE_DATABASE_ID = os.getenv("MODULE_DATABASE_ID")

# region Logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
# endregion


def get_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2021-05-13",
    }


def get_page(page_id):
    """Retrieves metadata for a specific page (Module or Seed)."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    return requests.get(url, headers=get_headers()).json()


def get_blocks(block_id):
    """Retrieves children blocks (Code Blocks) of a page."""
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    return requests.get(url, headers=get_headers()).json().get("results", [])


def find_seed_by_name(name):
    """Queries the Seed Database specifically."""
    url = f"https://api.notion.com/v1/databases/{SEED_DATABASE_ID}/query"
    payload = {"filter": {"property": "Reference", "title": {"contains": name}}}
    res = requests.post(url, headers=get_headers(), json=payload).json()
    print(
        f"🔍 Searching for Seed: '{name}'... Found {len(res.get('results', []))} match(es)."
    )
    return res["results"][0] if res.get("results") else None


def deploy_module(module_page_id, base_dir):
    """Fetches a module from the Module Database and writes it to disk."""
    page = get_page(module_page_id)
    props = page.get("properties", {})

    # Filename from the 'Reference' property
    filename = props["Reference"]["title"][0]["text"]["content"].strip()

    # Path sanitization
    raw_path = ""
    if "Path" in props and props["Path"]["rich_text"]:
        raw_path = props["Path"]["rich_text"][0]["text"]["content"].strip()

    sanitized_sub_path = os.path.normpath(raw_path.strip("/\\"))
    target_dir = os.path.join(base_dir, sanitized_sub_path)

    os.makedirs(target_dir, exist_ok=True)
    full_file_path = os.path.join(target_dir, filename)

    # 3. Extraction with safety checks
    blocks = get_blocks(module_page_id)
    code_content = None

    for b in blocks:
        print(b)

        if b["type"] == "code":
            # Check if 'rich_text' exists AND is not empty
            text = b["code"].get("text", [])
            if text:
                code_content = text[0]["text"]["content"]
                break  # Stop at the first valid code block
            else:
                logger.warning(f"Found empty code block in module: {filename}")

    if code_content:
        with open(full_file_path, "w", encoding="utf-8") as f:
            f.write(code_content)
        print(f"✔ Deployed: {os.path.relpath(full_file_path, base_dir)}")
        return full_file_path
    return None


def getAllSeeds():
    """
    Queries the SEED_DATABASE_ID and returns a list of all application seeds.
    """
    url = f"https://api.notion.com/v1/databases/{SEED_DATABASE_ID}/query"

    seeds = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(url, headers=get_headers(), json=payload)

        if response.status_code != 200:
            logger.error(f"Failed to fetch seeds: {response.text}")
            break

        data = response.json()

        for page in data.get("results", []):
            # Extract the title from the 'Reference' property
            title_list = page["properties"].get("Reference", {}).get("title", [])
            title = title_list[0]["text"]["content"] if title_list else "Untitled Seed"

            seeds.append({"name": title, "id": page["id"]})

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return seeds


def main():
    # Target Seed Name
    # Input seed name format: "_SEED, YYYY-MM-DD [App Name] (Description)"

    #seed_name = "_SEED, 2026-01-25 [Test] (Create Folders)"
    seed_name = input("Enter the Seed name (e.g., '_SEED, 2026-01-25 [App Name] (Description)'): ").strip()

    # Step 1: Locate the Seed in the SEED_DATABASE
    seed_page = find_seed_by_name(seed_name)

    if not seed_page:
        print(f"❌ Seed '{seed_name}' not found in Seed Database.")
        return

    # Step 2: Establish Workspace
    app_name = seed_name.split("(")[-1].strip(")")
    base_workspace = os.path.abspath(app_name)
    print("🚀 NMDO Deployer | Seed DB -> Module DB")
    print(f"📂 Workspace: {base_workspace}\n")

    # Step 3: Iterate through linked modules in the 'Modules' Relation property
    module_relations = seed_page["properties"].get("Modules", {}).get("relation", [])
    
    # Print each linked module's name for clarity
    if module_relations:
        print("Linked Modules:")
        for rel in module_relations:
            module_page = get_page(rel["id"])
            module_title = module_page["properties"]["Reference"]["title"][0]["text"]["content"]
            print(f"  - {module_title}")

    if not module_relations:
        print("⚠ No modules linked to this seed. Check your Notion Relation.")
        return

    for rel in module_relations:
        # The Relation contains the Module's Page ID
        print(f"\n🔗 Deploying Module ID: {rel['id']}")
        deploy_module(rel["id"], base_workspace)

    # Step 4: Execute final command
    cmd_prop = seed_page["properties"].get("Command", {}).get("rich_text", [])
    if cmd_prop:
        command = cmd_prop[0]["text"]["content"]
        print(f"\n▶ Running: {command}")
        subprocess.run(command, shell=True, cwd=base_workspace)


if __name__ == "__main__":
    main()
    
    
