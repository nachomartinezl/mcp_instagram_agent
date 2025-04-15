import json
import os

INPUT_PATH = "page_snapshots/feed_20250415_112159.json"

def describe_node(node):
    """Creates a simple description string for a node."""
    name = node.get('name', '').strip().replace('\n', ' ')
    role = node.get('role', 'unknown')
    focused = " (Focused)" if node.get("focused") else ""
    max_len = 70
    display_name = (name[:max_len] + '...') if len(name) > max_len else name
    return f"[{role}] '{display_name}'{focused}"

def print_subtree(node, level=0):
    """Recursively prints the entire tree with indentation."""
    indent = "  " * level
    print(f"{indent}└─ {describe_node(node)}")
    for child in node.get("children", []):
        print_subtree(child, level + 1)

# Check file exists
if not os.path.exists(INPUT_PATH):
    print(f"❌ Error: Input file not found at '{INPUT_PATH}'")
    exit()

# Load the full tree
try:
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        tree = json.load(f)
except json.JSONDecodeError as e:
    print(f"❌ Error decoding JSON: {e}")
    exit()
except Exception as e:
    print(f"❌ Error opening file: {e}")
    exit()

# Print the entire tree
print("📐 Printing full accessibility tree:\n")
print_subtree(tree)
