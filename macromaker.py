import sys
import zlib
import gzip
import json
import re
import os
from dataclasses import dataclass
gcsim_file = "Random_wait.gz"
export_target = "razer"
export_filename = "out"
export_dir = "./"
export_targets = [
    "razer",
    "ahk",
]

export_extensions = {
    "razer": ".xml",
    "ahk": ".ahk",
}

frame_length = 16.6666666667

default_key_delay = 3
extra_delay = 2
max_frame_dur = 60*29.5*2


def get_debug(filename) -> dict:
    try:
        with open(filename, 'rb') as file:
            data = file.read()
            try:
                data = gzip.decompress(data)
            except:
                data = zlib.decompress(data)
            data = json.loads(data)
            # perform some data validation to make sure the file is a gcsim config
            debug = data['logs']
            actions = [Action(item["char_index"], item["msg"], item["frame"])
                       for item in debug if item["event"] == "action"]
            return data
    except Exception as e:
        err(f"Did not find file \033[1;32m{filename}\033[0m or it is not a valid gcsim sample file")


razer_synapse_key_to_makecode = {
    "1": "2",
    "2": "3",
    "3": "4",
    "4": "5",
    "Click": "1",
    "Click , R": "2",
    "q": "16",
    "w": "17",
    "e": "18",
    "Space": "57",
}


@dataclass
class KeyAction():
    key: str
    delay: float

    def to_ahk(self):
        if self.delay <= 0 & self.key != None:
            raise ValueError(
                "Delay must be positive but got negative delay" + f"{self.delay=}, {self.delay=}")
        if self.key != None:
            return [
                f"Send, {{{self.key} down}}",
                f"Sleep, {int(self.delay*frame_length+0.5)}",
                f"Send, {{{self.key} up}}"
            ]
        else:
            return [
                f"Sleep, {int(self.delay*frame_length+0.5)}"
            ]

    def to_razer_xml(self):
        if self.delay < 0:
            raise ValueError(
                "Delay must be positive but got negative delay, " + f"{self.key=}, {self.delay=}")
        if self.key != None:
            ret = [""]
            if "Click" in self.key:
                ret = [f"""<Type>2</Type>
      <MouseEvent>
        <MouseButton>{razer_synapse_key_to_makecode[self.key]}</MouseButton>
        <State>0</State>
      </MouseEvent>
    </MacroEvent>
    <MacroEvent>
      <Delay>{int(self.delay*frame_length+0.5)}</Delay>
      <Type>2</Type>
      <MouseEvent>
        <MouseButton>{razer_synapse_key_to_makecode[self.key]}</MouseButton>
        <State>1</State>
      </MouseEvent>
    </MacroEvent>"""]
            else:
                ret = [f"""<Type>1</Type>
      <KeyEvent>
        <Makecode>{razer_synapse_key_to_makecode[self.key]}</Makecode>
      </KeyEvent>
      <Delay>{int(self.delay*frame_length+0.5)}</Delay>
    </MacroEvent>
    <MacroEvent>
      <Delay>{int(self.delay*frame_length+0.5)}</Delay>
      <Type>1</Type>
      <KeyEvent>
        <Makecode>{razer_synapse_key_to_makecode[self.key]}</Makecode>
        <State>1</State>
      </KeyEvent>
    </MacroEvent>"""]
            return ret
        else:
            return [
                f"""<MacroEvent>
      <Delay>{int(self.delay*frame_length+0.5)}</Delay>"""
            ]


msg_to_ignore: set[str] = {
    "executed wait",
    "executed pre action delay",
    "executed swap",
}

msg_to_key: dict[str, KeyAction] = {
    "executed skill": KeyAction("e", default_key_delay),
    "executed dash": KeyAction("Click , R", default_key_delay),
    "executed burst": KeyAction("q", default_key_delay),
    "executed attack": KeyAction("Click", default_key_delay),
    "executed charge": KeyAction("Click", 25),
    "executed aim": KeyAction("Click", 90),
    "executed high_plunge": KeyAction("Click", default_key_delay),
    "executed walk": KeyAction("w", default_key_delay),
    "executed jump": KeyAction("Space", default_key_delay),
}

# need custom overrides for different chars
overrides: dict[(str, str), KeyAction] = {
    ("ganyu", "executed aim"): KeyAction("Click", 103),
    ("diona", "executed skill"): KeyAction("e", 20),
    ("venti", "executed skill"): KeyAction("e", 10),
    # ("kazuha", "executed skill"): KeyAction("e", 24),
    ("zhongli", "executed skill"): KeyAction("e", 52),
    ("lyney", "executed aim"): KeyAction("Click", 100),
    ("neuvillette", "executed charge"): KeyAction("Click", 15)
}


@dataclass
class Action():
    char_index: int
    msg: str
    frame: int

    def __str__(self):
        return ' '.join([str(self.char_index), self.msg, 'on frame', str(self.frame)])


swapping_regex = re.compile("swapping [a-zA-Z ]+ to [a-zA-Z ]+")


def key_actions_to_ahk(key_actions: list[KeyAction]):
    script = [
        """#IfWinActive Genshin Impact
F8::"""]
    for key_act in key_actions:
        script += key_act.to_ahk()
    return "\n\t".join(script)


def key_actions_to_razer_synapse(key_actions: list[KeyAction]):

    xml_start = """<?xml version="1.0" encoding="utf-8"?>
<Macro xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <Name>gcsim macro</Name>
  <Guid>decde667-ec41-4f0d-9fee-e0751e18d2d0</Guid>
  <MacroEvents>
    """
    xml_end = """</MacroEvents>
  <IsFolder>false</IsFolder>
  <FolderGuid>00000000-0000-0000-0000-000000000000</FolderGuid>
</Macro>
"""

    script = [xml_start]
    for key_act in key_actions:
        script += key_act.to_razer_xml()
    script.append(xml_end)
    return "\n\t".join(script)


def main():
    data = get_debug(gcsim_file)
    debug = data["logs"]

    actions = [Action(item["char_index"], item["msg"], item["frame"])
               for item in debug if item["event"] == "action" and item["msg"] not in msg_to_ignore]
    key_actions: list[KeyAction] = [KeyAction(None, 1)]
    chars = [x['name'] for x in data["character_details"]]

    i = 0
    while i < len(actions):
        act = actions[i]
        if act.frame > max_frame_dur:
            break
        if re.match(swapping_regex, act.msg) != None:
            if i+1 < len(actions):
                swap_act = KeyAction(
                    str(actions[i+1].char_index+1), default_key_delay)
                key_actions.append(swap_act)
                key_actions.append(KeyAction(
                    None, actions[i+1].frame-actions[i].frame-swap_act.delay+extra_delay))
                # buffer swap by 3 frames
                if i >= 1 and actions[i-1].msg != "executed burst":
                    buffer = 0
                    key_actions[-3].delay -= buffer
                    key_actions[-1].delay += buffer
                else:
                    buffer = 0
                    key_actions[-3].delay -= buffer
                    key_actions[-1].delay += buffer + 0
        else:
            if (chars[act.char_index], act.msg) in overrides.keys():
                key_act = overrides[(chars[act.char_index], act.msg)]
            else:
                key_act = msg_to_key[act.msg]
            key_actions.append(key_act)
            if i + 1 < len(actions):
                key_actions.append(
                    KeyAction(None, actions[i+1].frame-actions[i].frame-key_act.delay+extra_delay))
            if act.msg == "executed charge":
                buffer = 0
                if i > 0 and re.match(swapping_regex, actions[i-1].msg) == None and actions[i-1].msg != "executed dash" and actions[i-1].msg != "executed jump" and actions[i-1].msg != "executed walk":
                    buffer = min(max(key_actions[-3].delay - 1, 14), 14)
                    if chars[act.char_index] == "neuvillette":
                        if actions[i-1].msg == "executed skill":
                            buffer = 19
                        if actions[i-1].msg == "executed burst":
                            buffer = 13
                print(f"{key_actions[-3].delay=}")
                key_actions[-3].delay -= buffer
                key_actions[-1].delay += buffer
                # key_actions[-1].delay -= extra_delay
            elif i > 0 and (actions[i-1].msg == "executed attack") and act.msg == "executed attack":
                buffer = 5
                key_actions[-3].delay -= buffer
                key_actions[-1].delay += buffer
                key_actions[-1].delay -= extra_delay
            elif i > 0 and actions[i-1].msg == "executed charge" and act.msg == "executed attack":
                # key_actions[-1].delay -= extra_delay
                pass
            elif act.msg == "executed dash":
                # Just make dashes 2 frames longer to fix issues with dash frames being too short
                key_actions[-1].delay += 0
            elif act.msg == "executed jump":
                # Just make dashes 2 frames longer to fix issues with dash frames being too short
                key_actions[-1].delay += 0
        i += 1
    if key_actions[-1].key == None:
        key_actions = key_actions[:-1]
    out_name = os.path.join(export_dir, export_filename)

    if not out_name.endswith(export_extensions[export_target]):
        out_name += export_extensions[export_target]
    try:
        with open(out_name, "w") as f:
            if export_target == "ahk":
                print(key_actions_to_ahk(key_actions), file=f)
            elif export_target == "razer":
                print(key_actions_to_razer_synapse(key_actions), file=f)
    except IOError:
        err(f"Could not save to file \033[1;32m{out_name}\033[0m")


def get_configs():
    global export_target
    global gcsim_file
    global export_filename
    global export_dir
    global max_frame_dur
    try:
        with open("config.json", "r") as f:
            data = json.load(f)
            if "gcsim_file" in data.keys() and "export_target" in data.keys():
                gcsim_file = str(data["gcsim_file"])
                export_target = str(data["export_target"]).lower()
                print(f"Exporting to {export_target}")
                if "export_filename" in data.keys():
                    export_filename = str(data["export_filename"])
                if "duration" in data.keys():
                    max_frame_dur = int(data["duration"])
                if "export_dir" in data.keys():
                    export_dir = str(data["export_dir"])
                if export_target not in export_targets:
                    nl = "\n\t"
                    err(
                        f"\033[1;32mexport_target\033[0m in config is incorrect.\nValid targets are: {nl}{nl.join(export_targets)}")
            else:
                err("\033[1;32mconfig.json\033[0m did not have one of \033[1;32mgcsim_config\033[0m or \033[1;32mexport_target\033[0m keys.\nIf you would like to have a fresh \033[1;32mconfig.json\033[0m file, please delete the current one")
    except FileNotFoundError:
        try:
            with open("config.json", "w") as f:
                config = {"gcsim_file": gcsim_file, "export_target": export_target,
                          "export_filename": export_filename, "export_dir": export_dir, "duration": max_frame_dur}
                json.dump(config, fp=f, indent=2)
        except IOError:
            print("Could not save config file")
    except Exception as e:
        err(e)
    if len(sys.argv) > 1:
        gcsim_file = sys.argv[1]


def err(msg):
    print(msg, file=sys.stderr)
    input("Press Enter to continue...")
    sys.exit(1)


get_configs()
main()
