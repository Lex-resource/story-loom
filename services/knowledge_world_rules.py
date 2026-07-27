from services.knowledge_constants import WORLD_RULE_CATEGORIES, WORLD_RULE_ROOT_LABEL


def build_world_rules_tree(items) -> dict:
    categories = world_rule_categories()
    nodes = [
        {"id": "root", "label": WORLD_RULE_ROOT_LABEL, "group": "root", "title": "世界设定根节点"}
    ]
    edges = []
    details = {}

    for category_key, category_name in categories.items():
        category_id = f"cat_{category_key}"
        nodes.append({
            "id": category_id,
            "label": category_name,
            "group": "category",
            "title": category_name,
        })
        edges.append({"from": "root", "to": category_id, "label": "类别"})

    for item in items:
        tag = world_rule_tag_for(item)
        nodes.append({
            "id": item.name,
            "label": item.name,
            "group": tag,
            "title": item.name,
        })
        edges.append({"from": f"cat_{tag}", "to": item.name, "label": "包含"})
        details[item.name] = {
            "tag": tag,
            "tag_display": categories[tag],
            "content": world_rule_content(item),
        }

    return {"nodes": nodes, "edges": edges, "details": details}


def world_rule_categories() -> dict:
    return {
        **WORLD_RULE_CATEGORIES,
        "confirmed": "已验真理",
    }


def world_rule_tag_for(item) -> str:
    rule_type = getattr(item, "rule_type", None) or item.attributes.get("type") or item.attributes.get("rule_type") or "rule"
    rule_type = str(rule_type).strip().lower()

    if rule_type in ["world_rule", "rule", "法则", "编译法则"]:
        return "rule"
    if rule_type in ["location", "空间", "运行空间", "地理"]:
        return "location"
    if rule_type in ["faction", "线程", "活动线程", "势力", "组织"]:
        return "faction"
    if rule_type in ["restriction", "禁忌", "限制禁忌", "限制"]:
        return "restriction"
    if rule_type in ["confirmed", "真理", "已验真理"]:
        return "confirmed"
    return "rule"


def world_rule_content(item) -> str:
    rules = []
    for key, value in item.attributes.items():
        if value not in (None, "") and key not in ("_free_text", "relationships", "type", "rule_type"):
            rules.append(f"{key}: {value}")

    body = item.body or item.attributes.get("_free_text", "")
    if body:
        for line in body.splitlines():
            line = line.strip().lstrip("-* ")
            if line:
                rules.append(line)

    return "\n".join(rules) or "暂无法则定义描述"
