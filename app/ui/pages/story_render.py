"""剧情数据的面板式呈现。

渲染规则逐条对照控制面板的 hPairs / hRecords / hOverviewRows：

* 字段名一律走中文词表，未知字段回退为“补充信息”，不出现原始字段名；
* 内部字段（编号、向量、原始载荷等）直接隐藏；
* 嵌套对象展开为缩进的子表，数组按条列出；
* 空值显示为 “—”，空集合显示为 “暂无”。
"""
from __future__ import annotations

import re
from html import escape

from .story_labels import (HELP, clean_description, display_value, fmt_time, is_hidden,
    label)
from .. import theme

_MACHINE_ACTOR = re.compile(r'^[a-z]+:|^[A-Za-z0-9_-]{25,}$')


def _key_style():
    return (f'color:{theme.color("key")};padding:7px 16px 7px 0;'
            'vertical-align:top;white-space:nowrap')


def _value_style():
    return f'color:{theme.color("text")};padding:7px 0;vertical-align:top'


def _note_style():
    return f'color:{theme.color("hint")};font-size:12px;padding:4px 0'


def _scalar(value, key):
    return escape(str(display_value(value, key))).replace('\n', '<br>')


def _wrap_table(rows, indent):
    """rows: 已组装好的 <tr> 字符串列表；indent 为嵌套层级。"""
    if not rows:
        return ''
    pad = f' style="padding-left:{indent * 18}px"' if indent else ''
    body = ''.join(f'<tr>{row}</tr>' for row in rows)
    return (f'<table width="100%" cellspacing="0" cellpadding="0" border="0"{pad}>'
            f'{body}</table>')


def _row_html(key, value, depth):
    caption = escape(label(key))
    help_text = HELP.get(str(key))
    note = f'<div style="{_note_style()}">{escape(clean_description(help_text))}</div>' if help_text else ''
    if isinstance(value, (dict, list)):
        cell = _nested(value, depth + 1, key) + note
    else:
        cell = f'<span style="{_value_style()}">{_scalar(value, key)}</span>' + note
    return f'<td style="{_key_style()}">{caption}</td><td style="{_value_style()}">{cell}</td>'


def _nested(value, depth, key):
    if depth > 8:
        return f'<span style="{_note_style()}">内容较长，可在“导出剧情数据”中查看。</span>'
    if isinstance(value, dict):
        rows = [ _row_html(k, v, depth) for k, v in value.items()
                 if v is not None and not is_hidden(k)
                 and (k != 'characterTraits' or (isinstance(v, list) and any(str(x).strip() for x in v))) ]
        return _wrap_table(rows, depth) if rows else f'<span style="{_note_style()}">暂无</span>'
    items = [item for item in value if item is not None]
    if not items:
        return f'<span style="{_note_style()}">暂无</span>'
    blocks = ''.join(f'<div style="padding:6px 0 6px {depth * 16}px">{pairs_html(item, depth + 1, key)}</div>'
                     if isinstance(item, (dict, list))
                     else f'<div style="color:{theme.color("text")};padding:4px 0 4px {depth * 16}px">{_scalar(item, key)}</div>'
                     for item in items)
    return blocks


def pairs_html(value, depth=0, key=''):
    """把任意剧情数据渲染为面板式定义表（供 QTextBrowser 使用）。"""
    if value is None:
        return f'<span style="{_note_style()}">—</span>'
    if isinstance(value, (dict, list)):
        return _nested(value, depth, key)
    return f'<span style="{_value_style()}">{_scalar(value, key)}</span>'


def record_html(record, prose_keys=('content', 'summary'), skip=()):
    """单条记录：正文以无标签段落呈现，其余字段按面板样式列出，内部字段隐藏。"""
    payload = {key: value for key, value in record.items()
               if not str(key).startswith('_') and not is_hidden(key) and key not in skip}
    prose = None
    for key in prose_keys:
        if payload.get(key):
            prose = payload.pop(key)
            break
    html = ''
    if prose is not None:
        html += f'<p style="color:{theme.color("text")};margin:0 0 8px">{_scalar(prose, "")}</p>'
    if payload:
        html += pairs_html(payload)
    return html or f'<span style="{_note_style()}">暂无</span>'


def rows_html(rows):
    """概况用的一行一对；空值与“—”自动省略，全部为空时返回空串。"""
    trs = [f'<td style="{_key_style()}">{escape(str(caption))}</td>'
           f'<td style="{_value_style()}">{escape(str(value))}</td>'
           for caption, value in rows.items()
           if isinstance(value, str) and value.strip() and value != '—']
    return _wrap_table(trs, 0)


def record_title(record):
    """列表项标题：类型 + 时间。时间走 fmtTime，不显示原始时间戳。"""
    kind = record.get('_category') or display_value(record.get('kind', record.get('scope', '记录')), 'kind')
    stamp = (record.get('occurredAt') or record.get('updatedAt') or record.get('createdAt')
             or record.get('notBefore') or '')
    return str(kind), (fmt_time(stamp) if stamp else '')


def actor_name(record):
    """发言者：隐藏机器标识，其余原样显示（对应面板 hTimelineActor）。"""
    actor = str(record.get('actor') or '')
    if actor == 'narrator':
        return '叙述'
    if actor == 'system':
        return '系统'
    return '' if _MACHINE_ACTOR.match(actor) else actor


def record_preview(record):
    """列表项摘要：正文/摘要/名称，压缩为单行。"""
    text = record.get('content') or record.get('summary') or record.get('name') or record.get('title') or ''
    return ' '.join(str(text).split())


def meta_line(*parts):
    """拼接元信息行，跳过空值与占位符。"""
    return ' · '.join(str(part) for part in parts if part not in (None, '', '—'))
