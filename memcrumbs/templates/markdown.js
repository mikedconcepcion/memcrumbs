/* A small, safe Markdown renderer for the dashboard's wiki reader. It builds DOM nodes only (textContent,
   setAttribute): page text is never parsed as HTML, and only http(s) links get an href. Covers what wiki
   pages use: headings, paragraphs, nested lists, task items, code fences, quotes, tables, rules, inline code,
   bold, italics, [text](url) and [[page]] links. */
const MD = (() => {
  "use strict";
  const INLINE = String.raw`(\x60+)([\s\S]*?)\1|\[\[([^\]|#\n]+)(?:#[^\]|\n]*)?(?:\|([^\]\n]+))?\]\]|\[([^\]\n]+)\]\(([^)\s]+)(?:\s+"[^"\n]*")?\)|\*\*([^*\n]+?)\*\*|__([^_\n]+?)__|(?<![\w*])\*([^*\n]+?)\*(?![\w*])|(?<![\w])_([^_\n]+?)_(?![\w])`;
  const ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
  const FENCE = /^\s*(\x60{3,}|~{3,})/;

  function el(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined && text !== null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }

  function inline(text, parent, ctx) {
    const re = new RegExp(INLINE, "g");
    let last = 0, m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      if (m[1]) parent.appendChild(el("code", m[2]));
      else if (m[3]) parent.appendChild(ctx.page(m[3].trim(), (m[4] || m[3]).trim()));
      else if (m[5]) parent.appendChild(link(m[5], m[6], ctx));
      else if (m[7] || m[8]) parent.appendChild(nest("strong", m[7] || m[8], ctx));
      else if (m[9] || m[10]) parent.appendChild(nest("em", m[9] || m[10], ctx));
      last = re.lastIndex;
      if (m[0] === "") re.lastIndex++;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
    return parent;
  }

  function nest(tag, text, ctx) { return inline(text, el(tag), ctx); }

  function link(text, url, ctx) {
    if (/^https?:\/\//i.test(url)) {
      const a = nest("a", text, ctx);
      a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.title = url;
      return a;
    }
    const md = /(?:^|\/)([^/#?]+)\.md(?:#.*)?$/i.exec(url);       // a relative link to another page
    if (md) {
      let name = md[1];
      try { name = decodeURIComponent(name); } catch (e) { /* a stray % stays as written */ }
      return ctx.page(name, text);
    }
    const span = nest("span", text, ctx);                         // a file path or another scheme: text only
    span.title = url;
    return span;
  }

  function cells(row) {
    return row.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, "|"));
  }

  function table(lines, i, out, ctx) {
    const head = cells(lines[i]), wrap = el("div", null, "tablewrap"), t = el("table"), thead = el("thead"), tr = el("tr");
    head.forEach(h => tr.appendChild(inline(h, el("th"), ctx)));
    thead.appendChild(tr); t.appendChild(thead);
    const body = el("tbody");
    i += 2;
    while (i < lines.length && /^\s*\|/.test(lines[i])) {
      const row = el("tr");
      cells(lines[i]).forEach(c => row.appendChild(inline(c, el("td"), ctx)));
      body.appendChild(row); i++;
    }
    t.appendChild(body); wrap.appendChild(t); out.appendChild(wrap);
    return i;
  }

  function list(lines, i, out, ctx) {
    const stack = [];                                             // [{indent, list}]
    let lastLi = null;
    while (i < lines.length) {
      const m = ITEM.exec(lines[i]);
      if (!m) {
        if (lastLi && /^\s{2,}\S/.test(lines[i])) { lastLi.appendChild(document.createTextNode(" ")); inline(lines[i].trim(), lastLi, ctx); i++; continue; }
        break;
      }
      const indent = m[1].replace(/\t/g, "    ").length, ordered = /\d/.test(m[2]);
      while (stack.length && indent < stack[stack.length - 1].indent) stack.pop();
      const top = stack[stack.length - 1];
      if (top && indent === top.indent && top.ordered !== ordered) stack.pop();    // "1." then "-": a new list
      if (!stack.length || indent > stack[stack.length - 1].indent) {
        const l = el(ordered ? "ol" : "ul"), parentLi = stack.length ? lastLi : null;
        (parentLi || out).appendChild(l);
        stack.push({indent, ordered, list: l});
      }
      const li = el("li");
      let text = m[3];
      const task = /^\[([ xX])\]\s+(.*)$/.exec(text);
      if (task) { li.appendChild(document.createTextNode(task[1] === " " ? "☐ " : "☑ ")); text = task[2]; }
      inline(text, li, ctx);
      stack[stack.length - 1].list.appendChild(li);
      lastLi = li; i++;
    }
    return i;
  }

  function blockStart(ln, next) {
    return /^\s*$/.test(ln) || FENCE.test(ln) || /^#{1,6}\s/.test(ln) || /^\s*>/.test(ln) || ITEM.test(ln) ||
      /^\s*([-*_])(\s*\1){2,}\s*$/.test(ln) || (/^\s*\|/.test(ln) && next !== undefined && /^\s*\|?\s*:?-{2,}/.test(next));
  }

  function render(src, out, ctx) {
    const lines = String(src).replace(/\r\n?/g, "\n").split("\n");
    let i = 0, m;
    while (i < lines.length) {
      const ln = lines[i];
      if (/^\s*$/.test(ln)) { i++; continue; }
      if ((m = FENCE.exec(ln))) {
        const buf = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith(m[1])) buf.push(lines[i++]);
        i++;
        const pre = el("pre", null, "code"); pre.appendChild(el("code", buf.join("\n"))); out.appendChild(pre);
        continue;
      }
      if ((m = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(ln))) {
        const leading = ctx.skipTitle && m[1].length === 1 && !out.childNodes.length;   // the reader shows the title
        if (!leading) {
          out.appendChild(inline(m[2], el("h" + Math.min(6, m[1].length + 1)), ctx));
        }
        ctx.skipTitle = null; i++; continue;
      }
      if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(ln)) { out.appendChild(el("hr")); i++; continue; }
      if (/^\s*>/.test(ln)) {
        const buf = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
        const q = el("blockquote"); render(buf.join("\n"), q, ctx); out.appendChild(q);
        continue;
      }
      if (/^\s*\|/.test(ln) && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || "")) { i = table(lines, i, out, ctx); continue; }
      if (ITEM.test(ln)) { i = list(lines, i, out, ctx); continue; }
      const buf = [ln.trim()];
      i++;
      while (i < lines.length && !blockStart(lines[i], lines[i + 1])) buf.push(lines[i++].trim());
      out.appendChild(inline(buf.join(" "), el("p"), ctx));
    }
    return out;
  }

  return {render};
})();
