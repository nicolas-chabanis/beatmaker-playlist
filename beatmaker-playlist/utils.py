from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Optional
import unidecode


@dataclass
class Track:
    """"""

    artist: str
    title: str

    def __repr__(self):
        return self.artist + " " + self.title


@dataclass
class Match:
    """"""

    track: Track = "NoTrack"
    id: Optional[str] = None

    def __repr__(self):
        return repr(self.track) + ": " + repr(self.id)


def clean_json_str(string: str):
    """"""
    return json.dumps(string, ensure_ascii=False).replace('"', "")


def normalize_string(string: str) -> str:
    """"""
    safe_string = unidecode.unidecode(string).lower()
    cleaned_string = re.sub(r"[\(\[].*?[\)\]]", "", safe_string)
    return cleaned_string


def write_json(data: dict, filename: str, directory: str = "debug") -> None:
    """"""
    dir = Path(directory)
    dir.mkdir(parents=True, exist_ok=True)
    safe_filename = "".join(c for c in filename if c.isalnum() or c in ("-", "_")) + ".json"
    file_path = dir / safe_filename
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
