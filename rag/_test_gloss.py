import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translate as T

cases = [
    {"kr": "이상", "en": "Yi Sang"},                          # whole-value name label
    {"kr": "체력이 10 이상일 때", "en": "When HP is 10 or more"},  # 이상=or-more, must NOT force 李箱
    {"kr": "돈키호테가 웃었다.", "en": "Don Quixote laughed."},   # proper noun in prose
    {"kr": "세븐 이상", "en": "Seven Yi Sang"},                # identity name
    {"kr": "관리자님, 잠시만요.", "en": "Manager, one moment."},
    {"kr": "", "en": "I cannot face this all alone."},          # EN prose: must NOT force Face/All/Free
    {"kr": "뿌이!", "en": "Ppui!"},                            # short user-confirmed term
]
for u in cases:
    print(f"KR={u['kr']!r:34} EN={u['en']!r:36} -> {T.glossary_hits(u)}")
