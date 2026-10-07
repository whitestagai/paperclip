def set_preferred_cmd(device_id):
    return ["lms", "link", "set-preferred-device", device_id]

def load_cmd(entry):
    cmd = ["lms", "load", entry["load_key"]]
    # Ohne --identifier laedt LM Studio unter dem Standardnamen des Modells.
    # Am Node WHITESTAG-AI waere das "gemma-4-31b-it" — genau die ID, die am
    # 03.10.2026 als Ursache von 204 max_iterations-Fehlern aus allen
    # Konfigurationen entfernt wurde und die dort weiterhin aufloest. Der
    # Lader wuerde eine zweite Instanz darunter erzeugen, auf einem Geraet
    # mit 48,99 von 56 GB belegt.
    ps_key = entry.get("ps_key")
    if ps_key and ps_key != entry["load_key"]:
        cmd += ["--identifier", ps_key]
    if entry.get("ctx") is not None:
        cmd += ["-c", str(entry["ctx"])]
    if entry.get("parallel") is not None:
        cmd += ["--parallel", str(entry["parallel"])]
    cmd.append("-y")
    return cmd
