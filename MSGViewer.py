#!/usr/bin/env python3
"""MSG Viewer — minimalist dark mail reader for macOS"""

import sys, os, subprocess, re, tempfile
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import extract_msg

try:
    from PIL import Image, ImageTk
    import io as _io
    _PIL = True
except ImportError:
    _PIL = False

# ─────────────────────────────────────────────────────────────────────────────
def fmt_date(raw):
    if not raw: return ""
    if isinstance(raw, datetime):
        return raw.strftime("%d. %B %Y  ·  %H:%M")
    return str(raw)

def fmt_sender(msg):
    name, email = "", ""
    for attr in ("senderName", "sender_name"):
        v = getattr(msg, attr, None)
        if v and isinstance(v, str) and v.strip():
            name = v.strip(); break
    for attr in ("senderEmail", "sender_email"):
        v = getattr(msg, attr, None)
        if v and isinstance(v, str) and v.strip():
            email = v.strip(); break
    if not email:
        raw = getattr(msg, "sender", None) or ""
        m = re.search(r"<([^>]+)>", str(raw))
        if m: email = m.group(1)
        elif "@" in str(raw): email = str(raw).strip()
    if name and email: return f"{name}  ·  {email}"
    return email or name

def fmt_recipients(recips, fallback=""):
    if not recips: return fallback or ""
    out = []
    for r in recips:
        name  = getattr(r, "name",  "") or ""
        email = getattr(r, "email", "") or ""
        out.append(name or email)
    return ",  ".join(filter(None, out)) or fallback

def clean_body(text):
    if not text: return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def html2text(html):
    if not html: return ""
    t = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S|re.I)
    t = re.sub(r"<script[^>]*>.*?</script>", "", t,   flags=re.S|re.I)
    t = re.sub(r"<br\s*/?>",  "\n", t, flags=re.I)
    t = re.sub(r"</p>",       "\n", t, flags=re.I)
    t = re.sub(r"<p[^>]*>",   "",   t, flags=re.I)
    t = re.sub(r"<[^>]+>",    "",   t)
    t = (t.replace("&nbsp;"," ").replace("&amp;","&")
          .replace("&lt;","<").replace("&gt;",">").replace("&quot;",'"')
          .replace("&#39;","'"))
    return clean_body(t)

# ─────────────────────────────────────────────────────────────────────────────
C = {
    "bg":      "#141414",
    "panel":   "#1a1a1a",
    "line":    "#262626",
    "text":    "#e8e8e8",
    "dim":     "#505050",
    "accent":  "#e8800a",
    "att":     "#2a1e0f",
    "att_txt": "#e8a05a",
    "sel":     "#e8800a",
}

F_LABEL = ("SF Pro Text",    10)
F_META  = ("SF Pro Text",    12)
F_SUBJ  = ("SF Pro Text", 14, "bold")
F_BODY  = ("SF Pro Text",    13)
F_MONO  = ("SF Mono",        11)

# ─────────────────────────────────────────────────────────────────────────────
class MSGViewer(tk.Tk):

    def __init__(self, path=None):
        super().__init__()
        self.title("MSG Viewer")
        # Restore saved window size
        prefs_path = os.path.expanduser("~/.msgviewer_prefs")
        default_geo = "1200x860"
        try:
            saved = open(prefs_path).read().strip()
            if re.match(r"\d+x\d+", saved):
                default_geo = saved
        except Exception:
            pass
        self.geometry(default_geo)
        self.configure(bg=C["bg"])
        self.minsize(720, 520)
        self._tmp = []
        self._inline_images = []
        self._prefs_path = prefs_path
        self._build_ui()
        self._register_apple_events()
        # Save geometry on resize
        self.bind("<Configure>", self._on_configure)
        if path and os.path.isfile(path):
            self.after(80, lambda: self._load(path))

    def _on_configure(self, event):
        if event.widget is self:
            geo = f"{self.winfo_width()}x{self.winfo_height()}"
            try:
                open(self._prefs_path, "w").write(geo)
            except Exception:
                pass
            # Keep subject wraplength in sync with window width
            wrap = max(300, self.winfo_width() - 80)
            try:
                self._lbl_subj.config(wraplength=wrap)
            except Exception:
                pass

    def _register_apple_events(self):
        try:
            self.createcommand("::tk::mac::OpenDocument", self._on_open_doc)
        except Exception:
            pass

    def _on_open_doc(self, *args):
        for p in args:
            p = p.strip()
            if p and os.path.isfile(p):
                self._load(p); break

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._make_topbar()
        self._make_header()
        self._make_body()
        self._make_statusbar()
        self.bind("<Command-o>", lambda _: self._open_dialog())

    def _make_topbar(self):
        bar = tk.Frame(self, bg=C["panel"], height=44)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Frame(bar, bg=C["line"], height=1).pack(side="bottom", fill="x")
        self._lbl_title = tk.Label(
            bar, text="MSG Viewer",
            bg=C["panel"], fg=C["dim"], font=(F_LABEL[0], 11)
        )
        self._lbl_title.pack(side="left", padx=22)
        open_lbl = tk.Label(
            bar, text="Open  ⌘O",
            bg=C["panel"], fg=C["accent"],
            font=(F_LABEL[0], 11), cursor="hand2"
        )
        open_lbl.pack(side="right", padx=22)
        open_lbl.bind("<Button-1>", lambda _: self._open_dialog())

    def _make_header(self):
        outer = tk.Frame(self, bg=C["bg"])
        outer.pack(fill="x", padx=36, pady=(28, 0))

        self._var_subj = tk.StringVar()
        self._lbl_subj = tk.Label(
            outer, textvariable=self._var_subj,
            bg=C["bg"], fg=C["text"],
            font=F_SUBJ, anchor="w",
            wraplength=880, justify="left"
        )
        self._lbl_subj.pack(fill="x", anchor="w")

        tk.Frame(outer, bg=C["bg"], height=18).pack()

        meta = tk.Frame(outer, bg=C["bg"])
        meta.pack(fill="x")

        self._var_from = tk.StringVar()
        self._var_to   = tk.StringVar()
        self._var_cc   = tk.StringVar()
        self._var_date = tk.StringVar()

        self._row_cc = None
        for key, var in [("From", self._var_from), ("To", self._var_to),
                          ("CC", self._var_cc), ("Date", self._var_date)]:
            row = tk.Frame(meta, bg=C["bg"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=key, bg=C["bg"], fg=C["dim"],
                     font=F_LABEL, width=5, anchor="w"
                     ).pack(side="left")
            tk.Label(row, textvariable=var, bg=C["bg"], fg=C["text"],
                     font=F_META, anchor="w", wraplength=830, justify="left"
                     ).pack(side="left", padx=(10, 0))
            if key == "CC":
                self._row_cc = row

        # Attachments — paperclip icon instead of text
        self._att_strip = tk.Frame(outer, bg=C["bg"])
        self._att_inner = tk.Frame(self._att_strip, bg=C["bg"])
        tk.Label(self._att_strip, text="📎",
                 bg=C["bg"], fg=C["dim"], font=(F_LABEL[0], 13)
                 ).pack(side="left")
        self._att_inner.pack(side="left", padx=(8, 0))

        tk.Frame(outer, bg=C["line"], height=1).pack(fill="x", pady=(22, 0))

    def _make_body(self):
        tabs = tk.Frame(self, bg=C["bg"])
        tabs.pack(fill="x", padx=36, pady=(14, 0))

        self._tab_btns = {}
        for label, key in [("Message", "text"), ("HTML Source", "html")]:
            btn = tk.Label(
                tabs, text=label,
                bg=C["bg"], fg=C["dim"],
                font=(F_LABEL[0], 11), cursor="hand2",
                padx=0, pady=4
            )
            btn.pack(side="left", padx=(0, 22))
            btn.bind("<Button-1>", lambda _, k=key: self._switch_tab(k))
            self._tab_btns[key] = btn

        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("M.Vertical.TScrollbar",
            background=C["line"], troughcolor=C["bg"],
            arrowcolor=C["dim"], borderwidth=0, relief="flat", width=5)

        self._pane_text = tk.Frame(self, bg=C["bg"])
        sb1 = ttk.Scrollbar(self._pane_text, style="M.Vertical.TScrollbar")
        sb1.pack(side="right", fill="y", padx=(0, 8))
        self._txt = tk.Text(
            self._pane_text,
            wrap="word", bg=C["bg"], fg=C["text"],
            font=F_BODY, relief="flat", bd=0,
            padx=36, pady=20,
            yscrollcommand=sb1.set, state="disabled",
            selectbackground=C["sel"], selectforeground="white",
            spacing1=0, spacing2=0, spacing3=6,
            insertbackground=C["text"],
        )
        self._txt.pack(fill="both", expand=True)
        sb1.config(command=self._txt.yview)

        self._pane_html = tk.Frame(self, bg="#0f0f0f")
        sb2 = ttk.Scrollbar(self._pane_html, style="M.Vertical.TScrollbar")
        sb2.pack(side="right", fill="y", padx=(0, 8))
        self._html_txt = tk.Text(
            self._pane_html,
            wrap="word", bg="#0f0f0f", fg="#7ec8a0",
            font=F_MONO, relief="flat", bd=0,
            padx=36, pady=20,
            yscrollcommand=sb2.set, state="disabled",
        )
        self._html_txt.pack(fill="both", expand=True)
        sb2.config(command=self._html_txt.yview)

        self._switch_tab("text")

    def _switch_tab(self, key):
        for k, b in self._tab_btns.items():
            b.config(fg=C["accent"] if k == key else C["dim"])
        if key == "text":
            self._pane_html.pack_forget()
            self._pane_text.pack(fill="both", expand=True, pady=(8, 0))
        else:
            self._pane_text.pack_forget()
            self._pane_html.pack(fill="both", expand=True, pady=(8, 0))

    def _make_statusbar(self):
        bar = tk.Frame(self, bg=C["panel"], height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Frame(bar, bg=C["line"], height=1).pack(side="top", fill="x")
        self._lbl_status = tk.Label(
            bar, text="",
            bg=C["panel"], fg=C["dim"],
            font=(F_LABEL[0], 10), anchor="w", padx=22
        )
        self._lbl_status.pack(fill="x", pady=5)

    # ── Load ──────────────────────────────────────────────────────────────────
    def _open_dialog(self):
        p = filedialog.askopenfilename(
            title="MSG-Datei öffnen",
            filetypes=[("Outlook Messages", "*.msg"), ("All Files", "*.*")]
        )
        if p: self._load(p)

    def _load(self, path):
        try:
            msg = extract_msg.Message(path)
        except Exception as e:
            messagebox.showerror("Fehler", f"Datei konnte nicht geöffnet werden:\n{e}")
            return

        subj = msg.subject or "(kein Betreff)"
        self._var_subj.set(subj)
        self.title(subj)
        self._lbl_title.config(text=subj[:64] + ("…" if len(subj) > 64 else ""))

        self._var_from.set(fmt_sender(msg))

        tr = getattr(msg, "to_recipient_objects", None)
        cr = getattr(msg, "cc_recipient_objects", None)
        self._var_to.set(fmt_recipients(tr, getattr(msg, "to", "") or ""))
        cc = fmt_recipients(cr, getattr(msg, "cc", "") or "")
        self._var_cc.set(cc)
        if self._row_cc:
            if cc: self._row_cc.pack(fill="x", pady=2)
            else:  self._row_cc.pack_forget()

        self._var_date.set(fmt_date(msg.date))

        plain = msg.body or ""
        html  = msg.htmlBody or ""
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")

        display = clean_body(plain) if plain.strip() else html2text(html)
        self._render_body(msg, display, html)
        self._set_text(self._html_txt, html or "(kein HTML-Body)")

        self._load_attachments(msg)

        sz  = os.path.getsize(path)
        szs = f"{sz/1024:.0f} KB" if sz < 1_048_576 else f"{sz/1_048_576:.1f} MB"
        self._lbl_status.config(
            text=f"{os.path.basename(path)}   ·   {szs}   ·   {fmt_date(msg.date)}")
        msg.close()

    def _set_text(self, w, content):
        w.config(state="normal")
        w.delete("1.0", "end")
        w.insert("1.0", content)
        w.config(state="disabled")

    def _render_body(self, msg, display_text, html):
        """Render body with inline images grouped horizontally per paragraph."""
        w = self._txt
        w.config(state="normal")
        w.delete("1.0", "end")
        self._inline_images = []

        if not _PIL or not html:
            w.insert("1.0", display_text)
            w.config(state="disabled")
            return

        # Build cid -> bytes map
        cid_map = {}
        for att in msg.attachments:
            cid = ""
            for attr in ("contentId", "cid"):
                v = getattr(att, attr, None) or ""
                v = v.strip("<>").strip()
                if v:
                    cid = v; break
            data = getattr(att, "data", None)
            if cid and data:
                cid_map[cid] = data

        def extract_cid(tag):
            m = re.search(r'src=["\']cid:([^"\'>\s]+)', tag, re.I)
            if m:
                return m.group(1).strip("<>").strip()
            return None

        def lookup_cid(cid):
            if cid in cid_map:
                return cid_map[cid]
            for key, data in cid_map.items():
                if key.split("@")[0] == cid.split("@")[0]:
                    return data
            return None

        # Only TRUE block-level tags split image groups
        # <span>, <a>, <o:p> etc. are INLINE — images around them stay together
        BLOCK_RE = re.compile(
            r"</?(?:p|div|table|tbody|tr|td|th|h[1-6]|ul|ol|li|blockquote|hr)"
            r"(?:\s[^>]*)?>|<br\s*/?>",
            re.I
        )
        IMG_RE = re.compile(r"<img[^>]+>", re.I)

        # Tokenise: split only on block tags and img tags
        # Everything else (inline tags, text) goes into "text" tokens
        tokens = []
        pos = 0
        combined = re.compile(r"(" + IMG_RE.pattern + r")|(" + BLOCK_RE.pattern + r")", re.I)
        for m in combined.finditer(html):
            before_chunk = html[pos:m.start()]
            if before_chunk:
                tokens.append(("text", before_chunk))
            tag = m.group(0)
            if re.match(r"<img", tag, re.I):
                cid = extract_cid(tag)
                if cid:
                    data = lookup_cid(cid)
                    if data:
                        tokens.append(("img", data))
                        pos = m.end()
                        continue
                # img without cid = treat as text
                tokens.append(("text", tag))
            else:
                tokens.append(("break", tag))
            pos = m.end()
        tail = html[pos:]
        if tail:
            tokens.append(("text", tail))

        def flush_text(buf):
            t = html2text(buf)
            if t:
                w.insert("end", t)

        def make_img_row(img_data_list):
            """Render a list of images side-by-side on one canvas."""
            pil_imgs = []
            for data in img_data_list:
                try:
                    pil_imgs.append(Image.open(_io.BytesIO(data)))
                except Exception:
                    pil_imgs.append(None)
            valid = [(img, data) for img, data in zip(pil_imgs, img_data_list) if img is not None]
            if not valid:
                return

            avail_w = max(200, self._txt.winfo_width() - 72)
            gap = 4

            # Split into rows if needed
            rows = []
            cur_row, cur_w = [], 0
            for img, data in valid:
                needed = (gap if cur_row else 0) + img.width
                if cur_row and cur_w + needed > avail_w:
                    rows.append(cur_row)
                    cur_row, cur_w = [(img, data)], img.width
                else:
                    cur_row.append((img, data))
                    cur_w += needed
            if cur_row:
                rows.append(cur_row)

            for row in rows:
                nat_total = sum(i.width for i, _ in row) + gap * (len(row) - 1)
                scale = min(1.0, avail_w / nat_total) if nat_total > avail_w else 1.0

                photos, row_h, row_w = [], 0, 0
                for img, data in row:
                    nw = max(1, int(img.width  * scale))
                    nh = max(1, int(img.height * scale))
                    photo = ImageTk.PhotoImage(img.resize((nw, nh), Image.LANCZOS))
                    self._inline_images.append(photo)
                    photos.append((photo, nw, nh))
                    row_h = max(row_h, nh)
                    row_w += nw + gap

                canvas_w = max(1, row_w - gap)
                canvas = tk.Canvas(w, width=canvas_w, height=row_h,
                                   bg=C["bg"], highlightthickness=0, bd=0)
                x = 0
                for photo, pw, ph in photos:
                    canvas.create_image(x, row_h // 2, anchor="w", image=photo)
                    x += pw + gap

                w.window_create("end", window=canvas, pady=2)

        text_buf = ""
        img_run  = []

        for kind, payload in tokens:
            if kind == "img":
                img_run.append(payload)
            elif kind == "text":
                # text interrupts an image run — flush images first
                if img_run:
                    if text_buf:
                        flush_text(text_buf); text_buf = ""
                    w.insert("end", "\n")
                    make_img_row(img_run)
                    w.insert("end", "\n")
                    img_run = []
                text_buf += payload
            else:  # block break
                if img_run:
                    if text_buf:
                        flush_text(text_buf); text_buf = ""
                    w.insert("end", "\n")
                    make_img_row(img_run)
                    img_run = []
                elif text_buf:
                    flush_text(text_buf); text_buf = ""
                tag_lower = payload.lower()
                if any(x in tag_lower for x in ["</p>", "<br", "</tr>", "</li>", "</h"]):
                    w.insert("end", "\n")

        # final flush
        if img_run:
            if text_buf:
                flush_text(text_buf); text_buf = ""
            w.insert("end", "\n")
            make_img_row(img_run)
            w.insert("end", "\n")
        if text_buf:
            flush_text(text_buf)

        w.config(state="disabled")

    def _load_attachments(self, msg):
        for w in self._att_inner.winfo_children():
            w.destroy()
        self._tmp.clear()
        atts = [a for a in msg.attachments if getattr(a, "data", None)]
        if not atts:
            self._att_strip.pack_forget(); return
        self._att_strip.pack(fill="x", pady=(6, 0))
        for att in atts:
            fname = att.longFilename or att.shortFilename or "Anhang"
            ext   = os.path.splitext(fname)[1]
            chip = tk.Label(
                self._att_inner, text=fname,
                bg=C["att"], fg=C["att_txt"],
                font=(F_LABEL[0], 11),
                padx=10, pady=4, cursor="hand2"
            )
            chip.pack(side="left", padx=(0, 6))
            def make_opener(data, name, e=ext):
                def _open(_=None):
                    t = tempfile.NamedTemporaryFile(
                        delete=False, suffix=e, prefix=name[:20])
                    t.write(data); t.close()
                    self._tmp.append(t.name)
                    subprocess.Popen(["open", t.name])
                return _open
            chip.bind("<Button-1>", make_opener(att.data, fname))

    def destroy(self):
        for f in self._tmp:
            try: os.unlink(f)
            except: pass
        super().destroy()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    MSGViewer(path=path).mainloop()
