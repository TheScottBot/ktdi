"""/hammeredofwitches: witch-finding tips from the Malleus Maleficarum (ktdi.features.malleus, lib/malleus.json)."""

import re

import pytest

from ktdi.features import malleus
from tests.fakes import Ctx, User, run

# The tips are hand-picked to leave out the book's torture, execution and child-harm passages. This keeps it that way.
GRIM = re.compile(r"tortur|\brack\b|torment|strappado|\bburn|\bflames?\b|\bstake\b|execut|put to death|\bkill|\bslay|"
                  r"\bslain|\bhang|gallows|\bnaked|\bstrip|\bshav|prison|\bchains?\b|secular arm|\bsentenc|punish|"
                  r"\bchild|\binfant|\bbab(y|ies)|midwi|unbaptized|\babort|\brape|put to the question|\bconfess", re.I)


def test_the_tips_are_tidy_and_torture_free():
    assert len(malleus.tips) >= 40
    for tip in malleus.tips:
        assert set(tip) == {"leaf", "text"} and isinstance(tip["leaf"], int) and 0 <= tip["leaf"] < 163
        assert not GRIM.search(tip["text"]), tip["text"]
        assert 40 < len(tip["text"]) < 1000 and tip["text"][-1] in ".?!", tip["text"]
        assert not re.search(r"[€©™¥|{}<>]|\s[,;.]|\b\d{2,}\b", tip["text"]), tip["text"]  # no OCR debris
    texts = [tip["text"] for tip in malleus.tips]
    assert len(set(texts)) == len(texts)


@pytest.mark.parametrize("tip", [{"leaf": 83, "text": "Witches *collect* members in a bird's nest."}])
def test_tip_embed(tip):
    embed = malleus.tip_embed(tip)
    assert embed.title == "🧹 Witch-finding tip"
    assert embed.description == "> Witches \\*collect\\* members in a bird's nest."
    assert embed.footer.text == "Malleus Maleficarum (1486), tr. Montague Summers (1928)"
    assert embed.url == "https://archive.org/details/bf-1569-a-2-i-5-1928/page/n83/mode/1up"


def test_hammeredofwitches_posts_a_random_tip(monkeypatch):
    picked = []
    monkeypatch.setattr(malleus.random, "choice", lambda tips: picked.append(tips) or tips[0])
    ctx = Ctx(User(1, "scott"))
    run(malleus.hammeredofwitches.callback(ctx))
    assert picked == [malleus.tips] and ctx.last.embed.description.startswith("> And what, then, is to be thought")
