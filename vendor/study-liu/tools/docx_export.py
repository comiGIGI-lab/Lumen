# docx_export.py — 零依赖 Word(.docx) 导出
#
# 为什么不用 python-docx：
#   后端一直刻意保持「只依赖标准库」的形态（见 requirements 说明与 DEPLOY.md），
#   而 .docx 本质就是一个 ZIP 包 + 若干 XML。用 zipfile 手写这几份 XML
#   完全够用，既不用在服务器上装包，也不会因为版本差异炸掉。
#
# 产出物在 Word / WPS / LibreOffice 均可直接打开。
#
# XML 骨架四件套（缺一个 Word 就报「文件损坏」）：
#   [Content_Types].xml            声明各部件类型
#   _rels/.rels                    指向主文档
#   word/_rels/document.xml.rels   指向 styles.xml
#   word/document.xml              正文
#   word/styles.xml                样式表

import io
import re
import zipfile
from datetime import datetime

_XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

# 正文/标题统一字体：微软雅黑在 Windows 与 WPS 上都在，且中英混排不难看
_FONT_ASCII = 'Calibri'
_FONT_EA = '微软雅黑'

# XML 1.0 不允许的控制字符（除 \t \n \r）。LLM 产出里偶尔混进 \x0b 之类，
# 不剔掉的话 Word 会直接判定文档损坏。
_ILLEGAL = re.compile(
    '[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffe\uffff]'
)


def _esc(text) -> str:
    """转义 XML 特殊字符并剔除非法控制字符。"""
    s = '' if text is None else str(text)
    s = _ILLEGAL.sub('', s)
    return (s.replace('&', '&amp;')
             .replace('<', '&lt;')
             .replace('>', '&gt;')
             .replace('"', '&quot;')
             .replace("'", '&apos;'))


def _run(text, bold=False, italic=False, color=None, size=None, font=None):
    """一个文本 run。size 单位是半磅（22 = 11pt）。"""
    rpr = []
    if font:
        rpr.append('<w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s"/>'
                   % (_esc(font), _esc(font), _esc(font)))
    if bold:
        rpr.append('<w:b/><w:bCs/>')
    if italic:
        rpr.append('<w:i/><w:iCs/>')
    if color:
        rpr.append('<w:color w:val="%s"/>' % _esc(color.lstrip('#')))
    if size:
        rpr.append('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (size, size))
    rpr_xml = '<w:rPr>%s</w:rPr>' % ''.join(rpr) if rpr else ''
    # xml:space="preserve" 保住首尾空格，否则 Word 会把缩进吃掉
    return '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr_xml, _esc(text))


def _para(runs='', style=None, align=None, before=None, after=None,
          indent=None, hanging=None, keep_next=False):
    """一个段落。runs 可以是字符串或已拼好的 run XML 片段。"""
    ppr = []
    if style:
        ppr.append('<w:pStyle w:val="%s"/>' % style)
    if keep_next:
        ppr.append('<w:keepNext/>')
    if before is not None or after is not None:
        ppr.append('<w:spacing%s%s/>' % (
            ' w:before="%d"' % before if before is not None else '',
            ' w:after="%d"' % after if after is not None else '',
        ))
    if indent is not None or hanging is not None:
        ppr.append('<w:ind%s%s/>' % (
            ' w:left="%d"' % indent if indent is not None else '',
            ' w:hanging="%d"' % hanging if hanging is not None else '',
        ))
    if align:
        ppr.append('<w:jc w:val="%s"/>' % align)
    ppr_xml = '<w:pPr>%s</w:pPr>' % ''.join(ppr) if ppr else ''

    if isinstance(runs, str) and runs.startswith('<w:r'):
        body = runs
    else:
        body = _run(runs)
    return '<w:p>%s%s</w:p>' % (ppr_xml, body)


def _cell(text, bold=False, width=None, header=False):
    """表格单元格。"""
    ppr = ''
    tcpr = []
    if width:
        tcpr.append('<w:tcW w:w="%d" w:type="dxa"/>' % width)
    if header:
        tcpr.append('<w:shd w:val="clear" w:color="auto" w:fill="F2EFEA"/>')
    tc = '<w:tcPr>%s</w:tcPr>' % ''.join(tcpr) if tcpr else ''
    runs = _run(text, bold=bold or header, size=20)
    return ('<w:tc>%s<w:p><w:pPr><w:spacing w:before="20" w:after="20"/>%s</w:pPr>'
            '%s</w:p></w:tc>' % (tc, ppr, runs))


def _table(rows, widths=None):
    """rows: [ [cell, cell, ...], ... ]，第一行当表头。"""
    if not rows:
        return ''
    borders = (
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="D8D2C8"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="D8D2C8"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D8D2C8"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="D8D2C8"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="D8D2C8"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="D8D2C8"/>'
        '</w:tblBorders>'
    )
    tblpr = '<w:tblPr><w:tblW w:w="0" w:type="auto"/>%s</w:tblPr>' % borders
    out = ['<w:tbl>', tblpr]
    for ri, row in enumerate(rows):
        cells = []
        for ci, val in enumerate(row):
            w = widths[ci] if widths and ci < len(widths) else None
            cells.append(_cell(val, header=(ri == 0), width=w))
        out.append('<w:tr>%s</w:tr>' % ''.join(cells))
    out.append('</w:tbl>')
    # 表格后补一个空段，免得紧贴下一段标题
    out.append('<w:p><w:pPr><w:spacing w:after="0"/></w:pPr></w:p>')
    return ''.join(out)


_PAGE_BREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


# ============================================================
# 样式表
# ============================================================

def _styles_xml():
    def style(sid, name, *, based='Normal', outline=None, size=None,
              bold=False, color=None, before=None, after=None, keep_next=False,
              indent=None, hanging=None):
        parts = ['<w:style w:type="paragraph" w:styleId="%s">' % sid]
        parts.append('<w:name w:val="%s"/>' % _esc(name))
        if based:
            parts.append('<w:basedOn w:val="%s"/>' % based)
        parts.append('<w:qFormat/>')
        ppr = []
        if outline is not None:
            ppr.append('<w:outlineLvl w:val="%d"/>' % outline)
        if keep_next:
            ppr.append('<w:keepNext/>')
        if before is not None or after is not None:
            ppr.append('<w:spacing%s%s/>' % (
                ' w:before="%d"' % before if before is not None else '',
                ' w:after="%d"' % after if after is not None else '',
            ))
        if indent is not None or hanging is not None:
            ppr.append('<w:ind%s%s/>' % (
                ' w:left="%d"' % indent if indent is not None else '',
                ' w:hanging="%d"' % hanging if hanging is not None else '',
            ))
        if ppr:
            parts.append('<w:pPr>%s</w:pPr>' % ''.join(ppr))
        rpr = ['<w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s"/>'
               % (_FONT_ASCII, _FONT_ASCII, _FONT_EA)]
        if bold:
            rpr.append('<w:b/><w:bCs/>')
        if color:
            rpr.append('<w:color w:val="%s"/>' % color)
        if size:
            rpr.append('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (size, size))
        parts.append('<w:rPr>%s</w:rPr>' % ''.join(rpr))
        parts.append('</w:style>')
        return ''.join(parts)

    return (_XML_HEAD +
            '<w:styles %s>' % _W +
            style('Normal', 'Normal', based=None, size=21, after=120)
            + style('Title', 'Title', based='Normal', size=48, bold=True,
                    color='191919', before=0, after=240, keep_next=True)
            + style('Heading1', 'heading 1', size=30, bold=True, color='191919',
                    before=360, after=160, outline=0, keep_next=True)
            + style('Heading2', 'heading 2', size=25, bold=True, color='191919',
                    before=280, after=120, outline=1, keep_next=True)
            + style('Heading3', 'heading 3', size=22, bold=True, color='4A4540',
                    before=200, after=100, outline=2, keep_next=True)
            + style('ListParagraph', 'List Paragraph', indent=420, hanging=220,
                    after=60)
            + style('Quote', 'Quote', size=20, color='4A4540', indent=420,
                    before=80, after=160)
            + style('Caption', 'Caption', size=18, color='808080', after=160)
            + '</w:styles>')


# ============================================================
# 组装器
# ============================================================

class DocxBuilder:
    """极简 docx 构造器。用法：b.heading('x', 1); b.paragraph('y'); data = b.render()"""

    def __init__(self):
        self._body = []

    def title(self, text):
        self._body.append(_para(text, style='Title'))
        return self

    def heading(self, text, level=1):
        lv = 1 if level < 1 else (3 if level > 3 else level)
        self._body.append(_para(text, style='Heading%d' % lv))
        return self

    def paragraph(self, text='', style=None, align=None):
        self._body.append(_para(text, style=style, align=align))
        return self

    def quote(self, text):
        self._body.append(_para(text, style='Quote'))
        return self

    def bullet(self, text, mark='•'):
        self._body.append(_para('%s  %s' % (mark, text), style='ListParagraph'))
        return self

    def numbered(self, text, n):
        self._body.append(_para('%s.  %s' % (n, text), style='ListParagraph'))
        return self

    def caption(self, text):
        self._body.append(_para(text, style='Caption'))
        return self

    def table(self, rows, widths=None):
        self._body.append(_table(rows, widths))
        return self

    def space(self):
        self._body.append('<w:p/>')
        return self

    def page_break(self):
        self._body.append(_PAGE_BREAK)
        return self

    def render(self) -> bytes:
        return build_docx(self._body)


def build_docx(body_parts) -> bytes:
    """把段落 XML 列表打成一个 .docx 字节流。"""
    document = (_XML_HEAD +
                '<w:document %s><w:body>%s' % (_W, ''.join(body_parts)) +
                # 节属性放在 body 末尾，定义纸张与页边距（A4，四边 2.1cm）
                '<w:sectPr>'
                '<w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1191" w:right="1191" w:bottom="1191" w:left="1191"'
                ' w:header="851" w:footer="992" w:gutter="0"/>'
                '</w:sectPr>'
                '</w:body></w:document>')

    content_types = (_XML_HEAD +
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '</Types>')

    rels = (_XML_HEAD +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')

    doc_rels = (_XML_HEAD +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        # [Content_Types].xml 必须是第一个条目，部分解析器对此敏感
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/_rels/document.xml.rels', doc_rels)
        z.writestr('word/styles.xml', _styles_xml())
        z.writestr('word/document.xml', document)
    return buf.getvalue()


# ============================================================
# 学习方案 → Word
# ============================================================

def _as_text(item):
    if item is None:
        return ''
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for k in ('title', 'name', 'text', 'label'):
            if item.get(k):
                return str(item[k]).strip()
        return ''
    return str(item).strip()


def _outline_rows(outline):
    """大纲 → [(章节名, [要点...])]。结构不统一，两种形态都要兜住。"""
    rows = []
    for i, ch in enumerate(outline or [], start=1):
        if isinstance(ch, dict):
            title = _as_text(ch) or '第 %d 章' % i
            points = ch.get('points') or ch.get('items') or ch.get('sections') or []
            if not isinstance(points, list):
                points = [points]
            points = [str(p).strip() for p in points if str(p).strip()]
            note = str(ch.get('summary') or ch.get('desc') or '').strip()
            if not points and note:
                points = [note]
            rows.append((title, points))
        else:
            rows.append((_as_text(ch) or '第 %d 章' % i, []))
    return rows


def _plan_rows(plan, plan_items=None):
    """计划 → [(天标签, 任务列表)]。优先用 plan_items（结构化的）。"""
    src = plan_items if isinstance(plan_items, list) and plan_items else plan
    rows = []
    for i, item in enumerate(src or [], start=1):
        if isinstance(item, dict):
            n = item.get('day') or i
            title = str(item.get('title') or '').strip()
            tasks = item.get('tasks') or []
            if not isinstance(tasks, list):
                tasks = [tasks]
            tasks = [str(t).strip() for t in tasks if str(t).strip()]
            label = '第 %s 天' % n
            if title:
                label += ' · ' + title
            rows.append((label, tasks))
        else:
            rows.append(('第 %d 天' % i, [_as_text(item)] if _as_text(item) else []))
    return rows


def _resource_rows(resources):
    rows = [['类型', '标题', '链接']]
    for r in resources or []:
        if isinstance(r, dict):
            rows.append([
                str(r.get('type') or '资源'),
                str(r.get('title') or '未命名资源'),
                str(r.get('url') or '—'),
            ])
        else:
            rows.append(['资源', _as_text(r), '—'])
    return rows if len(rows) > 1 else []


def render_plan_docx(result, course=None, generated_at=None) -> bytes:
    """把一份学习方案 result 渲染成 .docx 字节流。"""
    result = result or {}
    name = (course or result.get('course') or '学习方案').strip()
    profile = result.get('profile') or {}
    b = DocxBuilder()

    # ---- 封面 ----
    b.title(name)
    b.paragraph('智识有方 · 多模态教学智能体', style='Caption')
    b.space()

    date_text = generated_at or datetime.now().strftime('%Y-%m-%d')
    b.table([
        ['生成日期', '程度', '每日时长', '学习目标'],
        [
            str(date_text)[:10],
            str(profile.get('level') or '—'),
            str(profile.get('daily_hours') or '—'),
            str(profile.get('goal') or '—'),
        ],
    ], widths=[2400, 1800, 1800, 2400])

    # ---- 大纲 ----
    outline = _outline_rows(result.get('outline'))
    b.heading('一、课程大纲', 1)
    if outline:
        for i, (title, points) in enumerate(outline, start=1):
            b.heading('%02d  %s' % (i, title), 3)
            if points:
                for p in points:
                    b.bullet(p)
            else:
                b.caption('要点待补充')
    else:
        b.caption('大纲待写入。')

    # ---- 资源 ----
    b.heading('二、推荐资源', 1)
    res = _resource_rows(result.get('resources'))
    if res:
        b.table(res, widths=[1500, 4200, 4800])
    else:
        b.caption('资源待写入。')

    # ---- 计划 ----
    b.heading('三、每日计划', 1)
    days = _plan_rows(result.get('plan'), result.get('plan_items'))
    if days:
        for label, tasks in days:
            b.heading(label, 3)
            if tasks:
                for t in tasks:
                    b.bullet(t)
            else:
                b.caption('当日任务待补充')
    else:
        b.caption('计划待写入。')

    b.space()
    b.paragraph('LUMEN，拉丁语意为光。智识有方：光之所至，学有其方。', style='Caption')
    return b.render()


def suggest_docx_filename(course) -> str:
    """生成安全的 .docx 文件名。"""
    name = (course or '学习方案').strip() or '学习方案'
    for ch in '\\/:*?"<>|\r\n\t':
        name = name.replace(ch, '')
    name = name.strip(' .')[:60] or '学习方案'
    return '%s 学习方案.docx' % name
