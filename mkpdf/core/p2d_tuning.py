"""Ajustes al motor pdf2docx para documentos de oficina en español.

- Párrafos justificados de dos renglones se mantienen justificados.
- Los ítems de listas numeradas (1., 2., a), •) no se juntan en un solo párrafo.
"""
import re

from pdf2docx.common import constants
from pdf2docx.common.share import TextAlignment
from pdf2docx.text import Lines as _lines_mod
from pdf2docx.text import TextBlock as _tb_mod
from pdf2docx.text.Lines import Lines

_LIST_RE = re.compile(r"^\s*(\(?\d{1,2}[\.\)]|\(?[a-zA-Z][\)]|[a-z]\.|[•●▪■◦\-–—»✓])\s")
_MARKER_RE = re.compile(r"^\s*(\(?\d{1,2}[\.\)]|\(?[a-zA-Z][\)]|[a-z]\.|[•●▪■◦\-–—»✓])\s*$")
_applied = False


def _split_vertically_by_text(self, line_break_free_space_ratio: float, new_paragraph_free_space_ratio: float):
    rows = self.group_by_physical_rows()
    for row in rows:
        row.sort_in_line_order()
    num = len(rows)
    if num == 1:
        return rows
    W = max(row[-1].bbox[2] - row[0].bbox[0] for row in rows[1:])
    H = sum(row[0].bbox[3] - row[0].bbox[1] for row in rows) / num
    res = []
    lines = Lines()
    punc = tuple(constants.SENTENCE_END_PUNC)
    start_of_para = end_of_para = False
    start_of_sen = end_of_sen = False
    first = True
    for row in rows:
        row_text = "".join(l.text for l in row)
        end_of_sen = row_text.strip().endswith(punc)
        w = row[-1].bbox[2] - row[0].bbox[0]
        is_item = bool(_LIST_RE.match(row_text)) or (len(row) > 1 and bool(_MARKER_RE.match(row[0].text)))
        if not first and is_item:
            start_of_para = True
        elif end_of_sen and w / W <= 1.0 - line_break_free_space_ratio:
            end_of_para = True
        elif start_of_sen and (W - w) / H >= new_paragraph_free_space_ratio:
            start_of_para = True
        if end_of_para:
            lines.extend(row)
            res.append(lines)
            lines = Lines()
        elif start_of_para:
            if lines:
                res.append(lines)
            lines = Lines()
            lines.extend(row)
        else:
            lines.extend(row)
        start_of_sen = end_of_sen
        start_of_para = end_of_para = False
        first = False
    if lines:
        res.append(lines)
    return res


_orig_parse_alignment = _tb_mod.TextBlock._parse_alignment


def _parse_alignment(self, bbox, text_direction_param, line_separate_threshold,
                     lines_left_aligned_threshold, lines_right_aligned_threshold,
                     lines_center_aligned_threshold):
    alignment = _orig_parse_alignment(self, bbox, text_direction_param, line_separate_threshold,
                                      lines_left_aligned_threshold, lines_right_aligned_threshold,
                                      lines_center_aligned_threshold)
    try:
        if alignment == TextAlignment.LEFT:
            idx0, idx1, f = text_direction_param
            rows = self.lines.group_by_physical_rows()
            if len(rows) == 2:
                x1_first = rows[0][-1].bbox[idx1]
                x1_second = rows[1][-1].bbox[idx1]
                parent_right = bbox[idx1]
                # el primer renglón llega exacto al margen derecho y el segundo es más corto
                if abs(parent_right - x1_first) * f <= 2.5 and (x1_first - x1_second) * f > 10:
                    words = rows[0][0].text.split()
                    if len(words) > 4:
                        alignment = TextAlignment.JUSTIFY
    except Exception:
        pass
    return alignment


def apply():
    global _applied
    if _applied:
        return
    Lines.split_vertically_by_text = _split_vertically_by_text
    _tb_mod.TextBlock._parse_alignment = _parse_alignment
    _applied = True
