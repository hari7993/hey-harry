"""Small agent-desktop snapshots for tests; no command or real window is touched."""
import agentdesktop


RAW_ROLE = {"button": "button", "checkbox": "checkbox", "combobox": "combobox", "edit": "textfield",
            "link": "link", "listitem": "option", "menuitem": "menuitem", "radio": "radiobutton",
            "tab": "tab", "document": "document"}
ACTIONS = {"button": ["Click", "SetFocus"], "checkbox": ["Click", "Toggle", "SetFocus"],
           "combobox": ["Select", "SetFocus"], "edit": ["SetValue", "SetFocus"],
           "link": ["Click", "SetFocus"], "listitem": ["Click", "Select", "SetFocus"],
           "menuitem": ["Click", "SetFocus"], "radio": ["Click", "SetFocus"],
           "tab": ["Click", "Select", "SetFocus"], "document": ["SetFocus"]}


def node(name="", role="button", value=None, state=None, password=False, focus=False, rect=(0, 0, 10, 10),
         aid="", actions=None, children=None, raw_role=None, description="", item_type="", class_name="", ref=True,
         subrole="", role_description=""):
    """One raw snapshot node, using Harry's old role names unless raw_role is given."""
    raw = raw_role or RAW_ROLE.get(role, role)
    states = []
    if state == "on":
        states.append("checked")
    if password:
        states.append("secure")
    if focus:
        states.append("focused")
    if rect is None:
        bounds = None
    else:
        bounds = {"x": rect[0], "y": rect[1], "width": rect[2] - rect[0], "height": rect[3] - rect[1]}
    out = {"role": raw, "states": states, "available_actions": list(ACTIONS.get(role, []) if actions is None
                                                                       else actions),
           "children": list(children or ()), "item_type": item_type, "class_name": class_name}
    if name:
        out["name"] = name
    if value is not None:
        out["value"] = value
    if description:
        out["description"] = description
    if subrole:
        out["subrole"] = subrole
    if role_description:
        out["role_description"] = role_description
    if aid:
        out["native_id"] = {"kind": "automation_id", "value": aid}
    if bounds is not None:
        out["bounds"] = bounds
    if ref:
        out["_needs_ref"] = True
    return out


def snapshot(children=(), hwnd=7, title="Settings", app="systemsettings.exe", complete=True, root=None):
    """An agentdesktop.Snapshot with qualified refs assigned in tree order."""
    tree = root or node(title, raw_role="window", rect=(0, 0, 1200, 900), children=children, ref=False)
    number = [0]

    def assign(at):
        if at.pop("_needs_ref", False):
            number[0] += 1
            at["ref_id"] = f"@test{hwnd}:e{number[0]}"
        for child in at.get("children") or ():
            assign(child)
    assign(tree)
    data = {"app": app, "complete": complete, "snapshot_id": f"test{hwnd}", "tree": tree,
            "window": {"id": f"w-{hwnd}", "title": title}}
    return agentdesktop.Snapshot(data)


def element(*args, **kwargs):
    """A single element with a parent window and a usable ref."""
    return snapshot([node(*args, **kwargs)]).elements[1]
