"""/herbal and its data build (ktdi.features.herbal, ktdi.tools.herbal_build), from a tiny made-up ABBYY page."""

import csv
import html
import io

import pytest

from ktdi.features import herbal
from ktdi.tools import herbal_build as build
from tests.fakes import Ctx, User, run

SCOTT = User(1, "scott")


def char(c, x):
    return f'<charParams l="{x}" t="0" r="{x + 5}" b="10">{html.escape(c)}</charParams>'


def line(text, l, t, r, b):
    return (f'<line baseline="{b}" l="{l}" t="{t}" r="{r}" b="{b}"><formatting lang="Latin">'
            + "".join(char(c, l) for c in text) + "</formatting></line>")


def cell(*lines):
    return f'<cell width="10" height="10"><text><par>{"".join(lines)}</par></text></cell>'


ABBYY = f"""<?xml version="1.0" encoding="UTF-8"?>
<document xmlns="http://www.abbyy.com/FineReader_xml/FineReader6-schema-v1.xml">
<page width="1599" height="2500"><block blockType="Text"><text><par>{line("Not a table cell at all", 1, 1, 9, 9)}</par></text></block></page>
<page width="1599" height="2500"><block blockType="Table" l="0" t="0" r="1599" b="2500"><row>
{cell(line("A", 10, 10, 20, 20))}
{cell(line("rCP�3i*51", 30, 10, 60, 20))}
{cell(line("Calida, & humi-", 100, 200, 300, 230), line("da in 2.", 110, 240, 260, 270))}
{cell(line("Prurium eft fiacu.", 400, 500, 600, 530))}
{cell(line("calida, & HUMIDA in 2.", 700, 500, 900, 530))}
</row></block></page>
</document>""".encode()


def test_extract_keeps_word_like_table_cells():
    cells = build.extract_cells(ABBYY)
    assert [(c.id, c.page, c.latin) for c in cells] == [
        (1, 1, "Calida, & humida in 2."),  # lines joined, the hyphenated word rejoined
        (2, 1, "Prurium eft fiacu."),
    ]  # not the row letter, the noise, the text block, or the duplicate
    assert cells[0].box == (100, 200, 300, 270)  # around all its lines


@pytest.mark.parametrize("text, keep", [
    ("Faciunt infUdonem.", True), ("Horiulanum album.", True), ("A", False), ("rCP3i*51", False),
    ("C5c", False), ("27", False), ("Git>fst,8r c* , corricabilta Icuitcr.", True),
])
def test_looks_like_words(text, keep):
    assert build.looks_like_words(text) == keep


def test_sheet_has_a_translate_formula_per_row(tmp_path):
    path = tmp_path / "cells.csv"
    build.write_sheet(build.extract_cells(ABBYY), path)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows == [["id", "latin", "english"],
                    ["1", "Calida, & humida in 2.", '=GOOGLETRANSLATE(B2,"la","en")'],
                    ["2", "Prurium eft fiacu.", '=GOOGLETRANSLATE(B3,"la","en")']]


def test_merge_keeps_only_real_translations():
    cells = [build.Cell(1, 34, (1, 2, 3, 4), "Prurium eft fiacu."), build.Cell(2, 34, (1, 2, 3, 4), "Locus"),
             build.Cell(3, 35, (1, 2, 3, 4), "Abfejr"), build.Cell(4, 35, (1, 2, 3, 4), "Recens"),
             build.Cell(5, 36, (1, 2, 3, 4), "Rubcf")]
    downloaded = io.StringIO("id,latin,english\n1,x,With good luck it is time to go to the bathroom.\n2,x,#VALUE!\n"
                             "3,x,Loading...\n4,x,recens\n5,x,\n")
    assert build.merge(cells, list(csv.DictReader(downloaded))) == [
        {"page": 34, "box": [1, 2, 3, 4], "latin": "Prurium eft fiacu.",
         "english": "With good luck it is time to go to the bathroom."}]


ENTRY = {"page": 82, "box": [492, 1230, 649, 1287], "latin": "Horiulanum album.", "english": "White *gardener*."}


def test_crop_and_page_links():
    assert herbal.crop_url(82, [492, 1230, 649, 1287]) == (
        "https://iiif.archive.org/image/iiif/3/bub_gb_9lIU1a_-ddAC%2Fbub_gb_9lIU1a_-ddAC_jp2.zip%2F"
        "bub_gb_9lIU1a_-ddAC_jp2%2Fbub_gb_9lIU1a_-ddAC_0082.jp2/480,1218,181,81/max/0/default.jpg")
    assert "_0003.jp2/0,0,62,62/" in herbal.crop_url(3, [5, 5, 50, 50])  # padding stops at the page's edge
    assert herbal.page_url(82) == "https://archive.org/details/bub_gb_9lIU1a_-ddAC/page/n82/mode/1up"


def test_herbal_posts_a_random_box(monkeypatch):
    monkeypatch.setattr(herbal, "entries", [ENTRY])
    ctx = Ctx(SCOTT)
    run(herbal.herbal.callback(ctx))
    embed = ctx.last.embed
    assert embed.description == "## White \\*gardener\\*.\n-# The scanner read: Horiulanum album."
    assert embed.author.name == "📜 Tacuini sanitatis (1531), page 83" and embed.author.url.endswith("/page/n82/mode/1up")
    assert embed.image.url == herbal.crop_url(82, ENTRY["box"])


def test_herbal_before_the_translations_exist(monkeypatch):
    monkeypatch.setattr(herbal, "entries", [])
    ctx = Ctx(SCOTT)
    run(herbal.herbal.callback(ctx))
    assert "hasn't been translated yet" in ctx.last.content and ctx.last.private


def test_merge_finds_the_downloaded_sheet(tmp_path):
    import os
    (tmp_path / "other.csv").write_text("name,score\nx,1\n", encoding="utf-8")
    older = tmp_path / "herbal_cells - herbal_cells.csv"
    older.write_text("id,latin,english\n1,a,b\n", encoding="utf-8")
    newer = tmp_path / "herbal_cells - herbal_cells (1).csv"
    newer.write_text("﻿id,latin,english\n1,a,c\n", encoding="utf-8")  # Sheets can add a byte-order mark
    os.utime(older, (1, 1))
    assert build.find_download(tmp_path) == newer
    assert build.find_download(tmp_path / "nowhere") is None
