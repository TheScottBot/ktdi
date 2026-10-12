"""Reading the Text Creation Partnership's transcriptions of early printed books (ktdi.tools.tcp)."""

from ktdi.tools import tcp

BOOK = """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text>
<front><pb facs="tcp:1:1"/><pb facs="tcp:1:1"/><p>The title page.</p></front>
<body>
<div type="part"><head>OF THE <hi>VNICORNE.</hi></head>
<pb n="711" facs="tcp:1:2"/>
<p><seg rend="decorInit">W</seg>E are now come to the hiſtory of a beaſt<note place="margin">Plin.</note>, whereof
diuers people haue made great queſtion, fro<g ref="char:cmbAbbrStroke">̄</g> the <hi>Indians</hi> to vs.</p>
<p><figure><head>The figure of the Vnicorne.</head></figure>His horne is ſoueraigne, as <gap reason="illegible"
extent="1 word"><desc>(1 word)</desc></gap> writeth:</p>
<q><l>Not part of the paragraph,</l></q>
<p>
<pb n="712" facs="tcp:1:2"/>Of the Vnicorne thus the Poet: <q><l>A horne he hath,</l><l>and ſo he goes.</l></q>
And there an end.</p>
<div type="subpart"><head>OF THE SEA-<lb/>VNICORNE.</head>
<p>AMong the fiſhes there is one.</p>
</div>
</div>
</body></text></TEI>"""

def test_beasts_and_their_paragraphs():
    unicorn, sea = tcp.sections(BOOK, "beasts")
    assert (unicorn["key"], unicorn["head"]) == ("beasts:0", "OF THE VNICORNE")
    assert sea["head"] == "OF THE SEA-VNICORNE" and sea["paragraphs"][0]["text"] == "Among the fishes there is one."
    texts = [p["text"] for p in unicorn["paragraphs"]]  # Not the sea-unicorn's: that's its own section
    assert texts == [
        "We are now come to the history of a beast, whereof diuers people haue made great question, from the "
        "_Indians_ to vs.",  # The long s, the stroke for m, the drop capital; the side-note out
        "His horne is soueraigne, as … writeth:",  # The picture's caption out; an illegible word as "…"
        "Of the Vnicorne thus the Poet: A horne he hath, / and so he goes. And there an end."]
    # The page each starts on: the last starts a page, so its page break is inside it
    assert [(p["page"], p["folio"]) for p in unicorn["paragraphs"]] == [(1, "711"), (1, "711"), (2, "712")]
    assert sea["paragraphs"][0]["page"] == 2


def test_the_curation_is_checked_against_the_book():
    found = tcp.kept({"beasts": BOOK}, {"keep": {
        "beasts:0": {"head": "OF THE VNICORNE", "name": "Unicorn", "paragraphs": [0, 9]},
        "beasts:1": {"head": "OF THE BADGER", "name": "Badger", "paragraphs": [0]}}})
    assert [p["key"] for p in found["passages"]] == ["beasts:0:0"]
    assert found["missing"] == ["beasts:0:9", "beasts:1 (OF THE BADGER)"]  # Not there, or a different beast now


def test_a_paragraph_can_be_kept_only_up_to_some_words():
    found = tcp.kept({"beasts": BOOK}, {"keep": {"beasts:0": {"head": "OF THE VNICORNE", "name": "Unicorn",
                                                                 "paragraphs": [{"number": 2, "end": "he goes."},
                                                                                {"number": 0, "end": "not in it"}]}}})
    assert [p["text"] for p in found["passages"]] == [
        "Of the Vnicorne thus the Poet: A horne he hath, / and so he goes."]
    assert found["missing"] == ["beasts:0:0"]  # The words have to be in it


def test_highlight_is_a_word_the_scan_has():
    assert tcp.highlight("We are now come to the history of a beast of great question", "a QUESTION of hiſtory") \
        == "question"
    assert tcp.highlight("We are now come", "nothing alike") is None




def test_the_1560s_contractions():
    xml = """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div><head>¶ Of Herbes.</head>
<p>Take y<hi rend="sup">e</hi> herbe, y<hi rend="sup">t</hi> is cauſed of thē and cōmon mās, w<hi rend="sup">t</hi>
chaūces.<gap reason="duplicate" extent="1 page"><desc>(1 page duplicate)</desc></gap></p>
</div></body></text></TEI>"""
    section, = tcp.sections(xml, "secrets")
    assert section["head"] == "Of Herbes"
    assert section["paragraphs"][0]["text"] == "Take the herbe, that is caused of them and common mans, with chaunces."


def test_a_paragraph_can_have_its_own_name():
    found = tcp.kept({"beasts": BOOK}, {"keep": {"beasts:0": {"head": "OF THE VNICORNE", "name": "Unicorn",
                                                              "paragraphs": [0, {"number": 1, "name": "Horn",
                                                                                 "also": ["Alicorn"]}]}}})
    assert [(p["name"], p["also"]) for p in found["passages"]] == [("Unicorn", []), ("Horn", ["Alicorn"])]
