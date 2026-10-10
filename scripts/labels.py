#!/usr/bin/env python3
"""Print administrator-selected asset, batch and location labels as A4 PDF."""

import argparse
from io import BytesIO
from pathlib import Path
import sys

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

import inventory


BASE_URL = "https://github.com/BETA-SDC/inventory/blob/main/views"
FONT = "SDCLabelSans"
FONT_PATH = inventory.ROOT / "assets/fonts/NotoSansSC.ttf"


def label_data(data, identifiers):
    inventory.validate(data)
    entries = []
    for identifier in dict.fromkeys(identifiers):
        if identifier in data["location"]:
            entry = data["location"][identifier]
            entries.append({"id": identifier, "name": entry["name"], "kind": "存放位置",
                            "detail": "", "url": f"{BASE_URL}/locations/{identifier}.md"})
        else:
            inventory.require(identifier in data["object"], "Unknown label identifier")
            entry = data["object"][identifier]
            item = data["item"][entry["item"]]
            details = []
            if identifier.startswith("BAT-"):
                details.append(f"单位：{item['unit']}")
                if entry.get("expires_on"):
                    details.append(f"到期：{entry['expires_on']}")
            entries.append({"id": identifier, "name": entry["name"],
                            "kind": "公共资产" if identifier.startswith("AST-") else "物资批次",
                            "detail": "  ".join(details),
                            "url": f"{BASE_URL}/objects/{identifier}.md"})
    inventory.require(entries, "Select at least one registered identifier")
    return entries


def wrap(text, width, size):
    lines = []
    current = ""
    for character in text:
        if character in "\r\n":
            lines.append(current)
            current = ""
            continue
        if current and pdfmetrics.stringWidth(current + character, FONT, size) > width:
            lines.append(current)
            current = character
        else:
            current += character
    if current:
        lines.append(current)
    return lines


def draw_label(canvas, entry, x, y, width, height):
    canvas.setStrokeColor(HexColor("#b8bdc3"))
    canvas.setLineWidth(0.5)
    canvas.rect(x, y, width, height)
    padding = 4 * mm
    left = x + padding
    top = y + height - padding
    canvas.setFillColor(HexColor("#52606d"))
    canvas.setFont(FONT, 8)
    canvas.drawString(left, top - 8, f"SDC  /  {entry['kind']}")
    canvas.setFillColor(HexColor("#111111"))
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(left, top - 29, entry["id"])
    qr_size = 25 * mm
    text_width = width - qr_size - 3 * padding
    text_size = 10
    lines = wrap(entry["name"], text_width, text_size)
    while len(lines) > 3 and text_size > 6:
        text_size -= 0.5
        lines = wrap(entry["name"], text_width, text_size)
    inventory.require(len(lines) <= 3, "Label name too long: shorten the registered display name")
    canvas.setFont(FONT, text_size)
    for index, line in enumerate(lines):
        canvas.drawString(left, top - 46 - index * 12, line)
    if entry["detail"]:
        canvas.setFont(FONT, 7)
        canvas.drawString(left, y + 8 * mm, entry["detail"])
    canvas.setFont(FONT, 7)
    canvas.setFillColor(HexColor("#52606d"))
    canvas.drawString(left, y + 4 * mm, "扫码查看档案及申请入口")
    # ReportLab's QR widget includes a quiet zone around the code.
    widget = QrCodeWidget(entry["url"])
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(qr_size, qr_size, transform=[
        qr_size / (x1 - x0), 0, 0, qr_size / (y1 - y0),
        -x0 * qr_size / (x1 - x0), -y0 * qr_size / (y1 - y0),
    ])
    drawing.add(widget)
    qr_x = x + width - padding - qr_size
    qr_y = y + (height - qr_size) / 2
    renderPDF.draw(drawing, canvas, qr_x, qr_y)
    canvas.linkURL(entry["url"], (x, y, x + width, y + height), relative=0)


def create_pdf(data, identifiers):
    entries = label_data(data, identifiers)
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(FONT_PATH)))
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4, invariant=True)
    canvas.setTitle("SDC inventory labels")
    page_width, page_height = A4
    width, height, gap = 90 * mm, 45 * mm, 5 * mm
    margin_x = (page_width - 2 * width - gap) / 2
    margin_top = 20 * mm
    for index, entry in enumerate(entries):
        slot = index % 10
        if index and slot == 0:
            canvas.showPage()
        column, row = slot % 2, slot // 2
        x = margin_x + column * (width + gap)
        y = page_height - margin_top - (row + 1) * height - row * gap
        draw_label(canvas, entry, x, y, width, height)
        if slot == 0:
            canvas.setFont(FONT, 8)
            canvas.setFillColor(HexColor("#52606d"))
            canvas.drawString(margin_x, page_height - 12 * mm, "SDC 实物标签 / A4 原尺寸打印 / 标签 90 × 45 mm")
            canvas.drawString(margin_x, 12 * mm, f"第 {index // 10 + 1} 页")
    canvas.save()
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=inventory.ROOT)
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=inventory.ROOT / "output/pdf/labels.pdf")
    args = parser.parse_args()
    try:
        content = create_pdf(inventory.load(args.root), args.ids)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
        print(f"Created {args.output}")
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Labels failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
