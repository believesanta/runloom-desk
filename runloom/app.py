"""Desktop shell. Tk owns all widgets; workers communicate through a queue."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import queue
import sys
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else ROOT
from .theme import BG, PANEL, TEXT as INK, MUTED, ACCENT as TEAL, BORDER
from .theme import SIDEBAR, BUTTON, HOVER, PRIMARY, SELECTED, ERROR, dark_titlebar


def export_task(task):
    result = copy.deepcopy(task)
    result.pop('schedule', None)
    for p in result.get('parameters', []):
        if p.get('secret'):
            p.pop('default', None)
    return result


def duration(run):
    start = run.get('started_at') or run.get('created_at') or time.time()
    end = run.get('finished_at') or run.get('ended_at') or time.time()
    seconds = max(0, int(end - start))
    return f'{seconds // 60}m {seconds % 60:02d}s' if seconds >= 60 else f'{seconds}s'


def stamp(value):
    return time.strftime('%d %b · %H:%M:%S', time.localtime(value)) if value else '—'


class App:
    def __init__(self, root, data_dir):
        from .store import Store
        from .runner import Runner
        from .examples import builtins
        self.root, self.data_dir = root, Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.data_dir / 'runloom.db')
        self.runner = Runner(self.store)
        for task in builtins(ROOT, self.data_dir):
            if not any(t['id'] == task['id'] for t in self.store.list_tasks()):
                self.store.save_task(task)
        self.task = None
        self.run_id = None
        self.fields = {}
        self.drafts = {}
        self.page = 'Library'
        self.closing = False
        root.title('Runloom Desk — Local automation workbench')
        root.geometry('1220x820')
        root.minsize(960, 680)
        root.configure(bg=BG)
        self.styles()
        self.shell()
        self.show_library()
        dark_titlebar(root)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Control-f>', lambda e: self.focus_search())
        root.bind('<Control-Return>', lambda e: self.start())
        root.after(200, self.poll)

    def styles(self):
        self.root.option_add('*Font', ('Segoe UI', 10))
        for option, value in [('Background', BG), ('Foreground', INK), ('insertBackground', INK),
                              ('selectBackground', SELECTED), ('selectForeground', INK),
                              ('highlightBackground', BORDER), ('highlightColor', TEAL)]:
            self.root.option_add('*' + option, value)
        self.root.option_add('*TCombobox*Listbox.background', PANEL)
        self.root.option_add('*TCombobox*Listbox.foreground', INK)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background=BG, foreground=INK, font=('Segoe UI', 10))
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG)
        style.configure('TButton', padding=(12, 8), background=BUTTON, foreground=INK, borderwidth=0, focuscolor=TEAL)
        style.map('TButton', background=[('active', HOVER)], foreground=[('disabled', MUTED)])
        style.configure('Accent.TButton', background=PRIMARY, foreground=INK)
        style.map('Accent.TButton', background=[('active', HOVER)])
        style.configure('TEntry', fieldbackground=PANEL, foreground=INK, insertcolor=INK, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=7)
        style.map('TEntry', bordercolor=[('focus', TEAL)])
        style.configure('TCombobox', fieldbackground=PANEL, foreground=INK, background=BUTTON, arrowcolor=MUTED, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=6)
        style.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', INK)], selectbackground=[('readonly', PANEL)], selectforeground=[('readonly', INK)])
        style.configure('TCheckbutton', background=BG, foreground=INK, indicatorbackground=PANEL, indicatorforeground=INK)
        style.map('TCheckbutton', background=[('active', BG)], indicatorbackground=[('selected', PRIMARY), ('active', HOVER)])
        style.configure('Vertical.TScrollbar', background=BUTTON, troughcolor=BG, arrowcolor=MUTED, bordercolor=BG, lightcolor=BG, darkcolor=BG, width=12)
        style.map('Vertical.TScrollbar', background=[('active', HOVER)])
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, rowheight=38, borderwidth=0)
        style.configure('Treeview.Heading', background=BUTTON, foreground=MUTED, font=('Segoe UI', 10), padding=8)
        style.map('Treeview.Heading', background=[('active', HOVER)])
        style.map('Treeview', background=[('selected', SELECTED)], foreground=[('selected', INK)])
        style.configure('Horizontal.TProgressbar', background=PRIMARY, troughcolor=PANEL, borderwidth=0)

    def label(self, parent, text, size=10, color=INK, bold=False, bg=None, **kwargs):
        return tk.Label(parent, text=text, font=('Segoe UI', size, 'bold' if bold else 'normal'),
                        fg=color, bg=bg or parent.cget('bg'), anchor='w', **kwargs)

    def shell(self):
        side = tk.Frame(self.root, bg=SIDEBAR, width=180)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        self.label(side, 'Runloom', 17, INK, True).pack(anchor='w', padx=22, pady=(30, 4))
        self.label(side, 'Local scripts', 10, MUTED).pack(anchor='w', padx=22, pady=(0, 32))
        self.nav_buttons = {}
        for text, command in [('Library', self.show_library), ('Run history', self.show_history), ('Schedules', self.show_schedules), ('Settings', self.show_settings)]:
            button = tk.Button(side, text=text, command=command, anchor='w', bg=SIDEBAR, fg=MUTED, activebackground=SELECTED,
                      activeforeground=INK, relief='flat', bd=0, highlightthickness=1, highlightbackground=SIDEBAR, highlightcolor=TEAL, padx=12, pady=10, cursor='hand2')
            button.pack(fill='x', padx=10, pady=2)
            self.nav_buttons[text] = button
        bottom = tk.Frame(side, bg=SIDEBAR)
        bottom.pack(side='bottom', fill='x', padx=24, pady=24)
        self.label(bottom, 'On this device', 9, MUTED).pack(anchor='w')
        self.label(bottom, '0.1.2 · Mist', 9, MUTED).pack(anchor='w', pady=(5, 0))
        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(fill='both', expand=True)
        self.notice = tk.StringVar(value='Ready. Choose an automation to get started.')
        tk.Label(self.main, textvariable=self.notice, bg=SIDEBAR, fg=MUTED, anchor='w', padx=24, pady=9).pack(side='bottom', fill='x')
        self.content = tk.Frame(self.main, bg=BG)
        self.content.pack(fill='both', expand=True, padx=28, pady=22)

    def clear(self, title, subtitle):
        self.save_draft()
        for w in self.content.winfo_children():
            w.destroy()
        self.fields = {}
        self.page = title
        for name, button in self.nav_buttons.items():
            selected = name == title or (name == 'Run history' and title == 'Run details')
            button.configure(bg=SELECTED if selected else SIDEBAR, fg=INK if selected else MUTED)
        self.label(self.content, subtitle if title == 'Run details' else title, 23, INK, True).pack(anchor='w', pady=(6, 24))

    def save_draft(self):
        if self.task and self.fields:
            self.drafts[self.task['id']] = {k: v.get() for k, v in self.fields.items()}

    def focus_search(self):
        if self.page != 'Library': self.show_library()
        self.search.focus_set()

    def show_library(self):
        self.clear('Library', 'Small scripts. Useful work.')
        bar = tk.Frame(self.content, bg=BG)
        bar.pack(fill='x', pady=(0, 16))
        self.search_var = tk.StringVar()
        self.label(bar, 'Search  ', 10, MUTED).pack(side='left')
        self.search = ttk.Entry(bar, textvariable=self.search_var, width=35)
        self.search.pack(side='left')
        ttk.Button(bar, text='New automation', command=lambda: self.editor()).pack(side='right')
        ttk.Button(bar, text='Import', command=self.import_task).pack(side='right', padx=8)
        self.search_var.trace_add('write', lambda *args: self.fill_library())
        split = tk.PanedWindow(self.content, orient='horizontal', bg=BG, sashwidth=16, bd=0)
        split.pack(fill='both', expand=True)
        left = tk.Frame(split, bg=BG)
        self.library = tk.Listbox(left, bg=PANEL, fg=INK, selectbackground=SELECTED, selectforeground=INK,
                                  relief='flat', highlightthickness=1, highlightbackground=BORDER,
                                  font=('Segoe UI', 11), activestyle='none', exportselection=False)
        self.library.pack(fill='both', expand=True)
        self.library.bind('<<ListboxSelect>>', self.select_library)
        self.label(left, 'Ctrl+F  Search    ·    Ctrl+Enter  Run', 9, MUTED).pack(anchor='w', pady=10)
        self.detail = tk.Frame(split, bg=BG)
        split.add(left, minsize=230, width=280)
        split.add(self.detail, minsize=430)
        self.fill_library()

    def fill_library(self):
        query = self.search_var.get().lower()
        self.tasks = [t for t in self.store.list_tasks() if query in (t['name'] + ' ' + t.get('description', '')).lower()]
        self.library.delete(0, 'end')
        for t in self.tasks:
            self.library.insert('end', '  ' + t['name'])
        if self.tasks:
            index = next((i for i,t in enumerate(self.tasks) if self.task and t['id'] == self.task['id']), 0)
            self.library.selection_set(index)
            self.select_library()
        else:
            self.save_draft()
            self.task = None
            self.fields = {}
            for w in self.detail.winfo_children(): w.destroy()
            self.label(self.detail, 'No matching automations.', 14, MUTED).pack(pady=30)

    def select_library(self, event=None):
        selection = self.library.curselection()
        if not selection: return
        self.save_draft()
        self.task = self.tasks[selection[0]]
        self.fields = {}
        for w in self.detail.winfo_children(): w.destroy()
        self.label(self.detail, self.task.get('category', 'Personal'), 9, MUTED).pack(anchor='w')
        self.label(self.detail, self.task['name'], 19, INK, True).pack(anchor='w', pady=(7, 6))
        self.label(self.detail, self.task.get('description', ''), 10, MUTED, wraplength=510, justify='left').pack(anchor='w', pady=(0, 16))
        canvas = tk.Canvas(self.detail, bg=BG, highlightthickness=0, height=240)
        scroll = ttk.Scrollbar(self.detail, orient='vertical', command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        form = tk.Frame(canvas, bg=BG)
        item = canvas.create_window((0,0), window=form, anchor='nw')
        form.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=e.width))
        saved = self.drafts.get(self.task['id'], {})
        for p in self.task.get('parameters', []):
            self.label(form, p.get('label', p['id']) + (' *' if p.get('required') else ''), 10, INK, True).pack(anchor='w', pady=(8, 5))
            value = saved.get(p['id'], p.get('default', ''))
            flag = value if isinstance(value, bool) else str(value).lower() in ('true', '1')
            var = tk.BooleanVar(value=flag) if p['type'] == 'boolean' else tk.StringVar(value=value)
            self.fields[p['id']] = var
            row = tk.Frame(form, bg=BG)
            row.pack(fill='x', padx=(0, 8))
            if p['type'] == 'boolean':
                ttk.Checkbutton(row, text='Enabled', variable=var).pack(anchor='w')
            elif p['type'] == 'select':
                ttk.Combobox(row, textvariable=var, values=p.get('options', []), state='readonly').pack(fill='x')
            else:
                entry = ttk.Entry(row, textvariable=var, show='•' if p.get('secret') else '')
                entry.pack(side='left', fill='x', expand=True)
                if p['type'] in ('file', 'folder'):
                    ttk.Button(row, text='Browse', command=lambda v=var,t=p['type']: self.browse(v,t)).pack(side='left', padx=(6,0))
        actions = tk.Frame(self.detail, bg=BG)
        actions.pack(fill='x', pady=(18, 8))
        ttk.Button(actions, text='Run automation', style='Accent.TButton', command=self.start).pack(side='left')
        if self.task.get('preview'):
            ttk.Button(actions, text='Preview', command=lambda:self.start(True)).pack(side='left', padx=8)
        tools = tk.Frame(self.detail, bg=BG)
        tools.pack(fill='x')
        for title,command in [('Edit', lambda:self.editor(self.task)), ('Export', self.export_current), ('Schedule', self.schedule_dialog), ('Command', self.command_dialog)]:
            ttk.Button(tools, text=title, command=command).pack(side='left', padx=(0,5))

    def browse(self, var, kind):
        path = filedialog.askdirectory(parent=self.root) if kind == 'folder' else filedialog.askopenfilename(parent=self.root)
        if path: var.set(path)

    def values(self):
        from .manifest import validate_values
        return validate_values(self.task, {k:v.get() for k,v in self.fields.items()})

    def start(self, preview=False):
        if self.page != 'Library' or not self.task: return
        try:
            run_id = self.runner.start(self.task, self.values(), preview=preview)
            self.notice.set('Started ' + self.task['name'])
            self.show_run(run_id)
        except Exception as e: messagebox.showerror('Cannot start', str(e), parent=self.root)

    def command_dialog(self):
        from .manifest import bind_command, substitute
        try:
            command = bind_command(self.task, self.values())
            cwd = substitute(self.task.get('cwd', '{app}'), self.values())
            for p in self.task.get('parameters', []):
                if p.get('secret'):
                    secret = str(self.fields[p['id']].get())
                    if secret:
                        command = [c.replace(secret, '[redacted]') for c in command]
                        cwd = cwd.replace(secret, '[redacted]')
            self.text_dialog('Launch details', 'Executable and argument array:\n' + json.dumps(command, indent=2, ensure_ascii=False) + '\n\nWorking directory:\n' + cwd)
        except Exception as e: messagebox.showerror('Invalid parameters', str(e))

    def text_dialog(self, title, text):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry('760x500')
        widget = ScrolledText(win, wrap='word', font=('Consolas', 10), padx=15, pady=15)
        widget.pack(fill='both', expand=True)
        widget.insert('1.0', text)
        widget.configure(state='disabled')

    def show_history(self):
        self.clear('Run history', 'Every run has a story.')
        tree = ttk.Treeview(self.content, columns=('name','status','start','duration'), show='headings')
        for col,title,width in [('name','AUTOMATION',240),('status','STATUS',120),('start','STARTED',180),('duration','DURATION',90)]:
            tree.heading(col,text=title); tree.column(col,width=width)
        tree.pack(fill='both',expand=True)
        for r in self.store.list_runs():
            tree.insert('', 'end', iid=r['id'], values=(r.get('name',r.get('task_id','Run')), r['status'], stamp(r.get('started_at')),duration(r)))
        tree.bind('<Double-1>', lambda e:self.show_run(tree.selection()[0]) if tree.selection() else None)
        ttk.Button(self.content,text='Open selected run',command=lambda:self.show_run(tree.selection()[0]) if tree.selection() else None).pack(anchor='e',pady=12)

    def show_run(self, run_id):
        run = self.store.get_run(run_id)
        if not run: return
        self.clear('Run details', run.get('name', run.get('task_id','Automation')))
        self.run_id = run_id
        top = tk.Frame(self.content,bg=BG); top.pack(fill='x')
        self.run_status = self.label(top,'',12,TEAL,True); self.run_status.pack(side='left')
        ttk.Button(top,text='Stop',command=lambda:self.runner.cancel(run_id)).pack(side='right')
        ttk.Button(top,text='Use these parameters',command=lambda:self.replay(run_id)).pack(side='right',padx=8)
        self.progress = ttk.Progressbar(self.content,mode='indeterminate'); self.progress.pack(fill='x',pady=15)
        self.log = ScrolledText(self.content,bg=SIDEBAR,fg=INK,insertbackground=INK,relief='flat',font=('Consolas',10),height=13,padx=15,pady=14,wrap='word')
        self.log.pack(fill='both',expand=True)
        self.label(self.content,'Output files',10,MUTED).pack(anchor='w',pady=(16,5))
        self.artifacts = tk.Listbox(self.content,height=4,bg=PANEL,fg=INK,relief='flat',selectbackground=SELECTED,selectforeground=INK)
        self.artifacts.pack(fill='x')
        self.artifacts.bind('<Double-1>',lambda e:self.open_artifact())
        output_actions=tk.Frame(self.content,bg=BG);output_actions.pack(fill='x',pady=7)
        ttk.Button(output_actions,text='Open output location',command=self.open_artifact).pack(side='right')
        ttk.Button(output_actions,text='Preview selected file',command=self.preview_artifact).pack(side='right',padx=8)
        self.last_log = None
        self.refresh_run()

    def refresh_run(self):
        if self.page != 'Run details': return
        run = self.store.get_run(self.run_id)
        if not run:return
        state = run['status']
        self.run_status.configure(text=f'{state.upper().replace("_"," ")}   ·   {duration(run)}' + ('   ·   PREVIEW' if run.get('preview') else ''))
        text = run.get('logs','')
        if isinstance(text,list):text='\n'.join(str(x) for x in text)
        if run.get('error'): text += '\n' + str(run['error'])
        if text != self.last_log:
            self.log.configure(state='normal'); self.log.delete('1.0','end'); self.log.insert('end',text or 'Waiting for output…'); self.log.configure(state='disabled'); self.log.see('end'); self.last_log=text
        progress = run.get('progress')
        self.progress.stop()
        if progress is not None:
            self.progress.configure(mode='determinate',value=progress)
        elif state in ('running','queued'):
            self.progress.configure(mode='indeterminate'); self.progress.start(15)
        else: self.progress.configure(mode='determinate',value=0)
        self.artifact_paths = [a.get('path') if isinstance(a,dict) else a for a in run.get('artifacts',[])]
        labels = [f'{Path(path).name}  ·  {Path(path).parent.name}' for path in self.artifact_paths]
        current = tuple(self.artifacts.get(0,'end'))
        if current != tuple(labels):
            self.artifacts.delete(0,'end')
            for label in labels:self.artifacts.insert('end',label)

    def open_artifact(self):
        selected=self.artifacts.curselection()
        if not selected:return
        path=Path(self.artifact_paths[selected[0]])
        if not path.exists():messagebox.showerror('Output unavailable','The file has been moved or removed.');return
        self.open_folder(path if path.is_dir() else path.parent)

    def preview_artifact(self):
        selected=self.artifacts.curselection()
        if not selected:return
        path=Path(self.artifact_paths[selected[0]])
        try:
            if path.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.gif','.bmp'):
                from PIL import Image, ImageTk
                with Image.open(path) as source:
                    source.thumbnail((820,580))
                    picture=ImageTk.PhotoImage(source.copy())
                win=tk.Toplevel(self.root);win.title(path.name)
                label=tk.Label(win,image=picture,bg=BG);label.image=picture;label.pack(padx=20,pady=20)
            elif path.suffix.lower() in ('.txt','.json','.csv','.md','.log'):
                with path.open('r',encoding='utf-8',errors='replace') as source:
                    text=source.read(262145)
                self.text_dialog(path.name,text[:262144]+('\n[Preview truncated]' if len(text)>262144 else ''))
            else:messagebox.showinfo('Preview unavailable','Use Open output location to inspect this file with an appropriate application.')
        except Exception as e:messagebox.showerror('Cannot preview output',str(e))

    def open_folder(self,path):
        try:
            if sys.platform=='win32':os.startfile(str(path))
            else:messagebox.showinfo('Location',str(path))
        except OSError as e:messagebox.showerror('Cannot open folder',str(e))

    def replay(self,run_id):
        run=self.store.get_run(run_id)
        if not run:return
        task=next((t for t in self.store.list_tasks() if t['id']==run['task_id']),None)
        if not task:messagebox.showinfo('Automation unavailable','Import this automation before using its parameters.');return
        values=run.get('values',{})
        values={k:v for k,v in values.items() if not any(p['id']==k and p.get('secret') for p in task.get('parameters',[]))}
        self.save_draft()
        self.fields={}
        self.task=task;self.drafts[task['id']]=values;self.show_library()

    def editor(self,task=None,imported=None):
        from .manifest import validate_manifest
        value=copy.deepcopy(task or imported) if (task or imported) else {'schema_version':1,'id':'my-script','name':'My script','description':'What this automation does.','category':'Personal','executable':'{python}','args':['-c','print("Hello from Runloom Desk")'],'cwd':str(ROOT),'parameters':[],'timeout':60,'allow_parallel':False,'preview':False}
        value.pop('schedule', None)
        win=tk.Toplevel(self.root);win.title('Automation manifest');win.geometry('850x650');win.configure(bg=BG)
        self.label(win,'Edit the manifest',20,INK,True).pack(anchor='w',padx=20,pady=(20,5))
        self.label(win,'Only add scripts you trust. Saving does not execute code.',10,MUTED).pack(anchor='w',padx=20,pady=(0,12))
        box=ScrolledText(win,font=('Consolas',11),undo=True);box.pack(fill='both',expand=True,padx=20);box.insert('1.0',json.dumps(value,indent=2,ensure_ascii=False))
        def save():
            try:
                parsed=json.loads(box.get('1.0','end'))
                parsed.pop('schedule',None)
                if task:
                    latest=next((t for t in self.store.list_tasks() if t['id']==task['id']),None)
                    if latest and latest.get('schedule'):parsed['schedule']=latest['schedule']
                parsed=validate_manifest(parsed)
                if task and parsed['id']!=task['id']:raise ValueError('Keep the stable ID when editing; import a copy to create another automation.')
                if not task and any(t['id']==parsed['id'] for t in self.store.list_tasks()):raise ValueError('This ID already exists. Choose a new ID.')
                self.store.save_task(parsed)
                self.save_draft()
                if task and latest and parsed['parameters'] != latest['parameters']:
                    self.drafts.pop(parsed['id'],None)
                self.fields={}
                win.destroy();self.show_library();self.notice.set('Automation saved. Review its command before the first run.')
            except Exception as e:messagebox.showerror('Invalid manifest',str(e),parent=win)
        ttk.Button(win,text='Save automation',style='Accent.TButton',command=save).pack(anchor='e',padx=20,pady=15)

    def import_task(self):
        from .manifest import validate_manifest
        path=filedialog.askopenfilename(filetypes=[('Automation manifest','*.json')])
        if not path:return
        try:
            task=validate_manifest(json.loads(Path(path).read_text(encoding='utf-8')))
            task.pop('schedule',None)
            if any(t['id']==task['id'] for t in self.store.list_tasks()):
                raise ValueError('This ID already exists. Edit the existing automation or use a new ID in the imported file.')
            self.editor(imported=task)
        except Exception as e:messagebox.showerror('Cannot import',str(e))

    def export_current(self):
        if not self.task:return
        path=filedialog.asksaveasfilename(defaultextension='.json',initialfile=self.task['id']+'.json')
        if path:
            try:Path(path).write_text(json.dumps(export_task(self.task),indent=2,ensure_ascii=False),encoding='utf-8');self.notice.set('Manifest exported. Schedules and secret defaults are excluded.')
            except OSError as e:messagebox.showerror('Cannot export',str(e))

    def schedule_dialog(self):
        if not self.task:return
        try: values=self.values()
        except Exception as e:messagebox.showerror('Parameters required',str(e));return
        if any(p.get('secret') for p in self.task.get('parameters',[])):
            messagebox.showinfo('Manual run required','Automations with secret fields cannot be scheduled in this version.');return
        scheduled_task = copy.deepcopy(self.task)
        win=tk.Toplevel(self.root);win.title('Schedule automation');win.geometry('460x340');win.configure(bg=BG)
        self.label(win,'Keep useful work on time.',19,INK,True).pack(padx=20,pady=20)
        kind=tk.StringVar(value='interval');amount=tk.StringVar(value='60')
        ttk.Combobox(win,textvariable=kind,values=['interval','daily'],state='readonly').pack(fill='x',padx=20)
        self.label(win,'Interval: minutes  ·  Daily: HH:MM (local time)',10,MUTED).pack(padx=20,pady=10)
        ttk.Entry(win,textvariable=amount).pack(fill='x',padx=20)
        self.label(win,'Runs while the app is open. Missed runs coalesce\ninto one run on resume; no automatic retry.',10,MUTED,justify='left').pack(padx=20,pady=15)
        def save():
            from .scheduler import next_run
            try:
                schedule={'kind':kind.get(),'values':values}
                if kind.get()=='interval':schedule['seconds']=int(amount.get())*60
                else:schedule['time']=amount.get()
                schedule['next_at']=next_run(schedule,time.time())
                current = next(t for t in self.store.list_tasks() if t['id']==scheduled_task['id'])
                current['schedule']=schedule;self.store.save_task(current);win.destroy();self.show_schedules()
            except Exception as e:messagebox.showerror('Invalid schedule',str(e),parent=win)
        ttk.Button(win,text='Save schedule',style='Accent.TButton',command=save).pack(pady=8)

    def show_schedules(self):
        self.clear('Schedules','A little rhythm for your work.')
        self.label(self.content,'Local time • App must remain open • Missed runs coalesce into one',10,MUTED).pack(anchor='w',pady=(0,15))
        tasks=[t for t in self.store.list_tasks() if t.get('schedule')]
        if not tasks:self.label(self.content,'No schedules yet. Choose an automation in Library, then Schedule.',12,MUTED).pack(anchor='w',pady=30)
        for task in tasks:
            s=task['schedule'];row=tk.Frame(self.content,bg=PANEL,padx=18,pady=16);row.pack(fill='x',pady=5)
            self.label(row,task['name'],13,INK,True).pack(anchor='w')
            self.label(row,f"{s['kind'].title()}  ·  Next: {stamp(s.get('next_at'))}  ·  Last: {stamp(s.get('last_at'))}",10,MUTED).pack(anchor='w',pady=5)
            if s.get('error'):self.label(row,s['error'],10,ERROR,wraplength=600).pack(anchor='w')
            ttk.Button(row,text='Disable schedule',command=lambda t=task:self.disable_schedule(t)).pack(anchor='e')

    def disable_schedule(self,task):
        current=next((t for t in self.store.list_tasks() if t['id']==task['id']),None)
        if current:
            current.pop('schedule',None)
            self.store.save_task(current)
        self.show_schedules()

    def show_settings(self):
        self.clear('Settings','Your workspace stays yours.')
        self.label(self.content,'WORKSPACE LOCATION',9,TEAL,True).pack(anchor='w')
        self.label(self.content,str(self.data_dir),11,INK,wraplength=750,justify='left').pack(anchor='w',pady=10)
        ttk.Button(self.content,text='Open workspace folder',command=lambda:self.open_folder(self.data_dir)).pack(anchor='w',pady=5)
        self.label(self.content,'Runloom Desk 0.1.2\nPython '+sys.version.split()[0]+' · Tk '+str(tk.TkVersion)+'\n\nTrusted scripts execute with your user permissions.\nClosing the app stops running tasks and pauses schedules.\n\nTo choose another workspace, launch with --data-dir PATH.\nHistory and configuration stay in the workspace SQLite database.',11,MUTED,justify='left',wraplength=700).pack(anchor='w',pady=25)
        ttk.Button(self.content,text='Read manifest guide',command=lambda:self.text_dialog('Manifest guide',(ROOT/'docs'/'manifest.md').read_text(encoding='utf-8'))).pack(anchor='w')

    def tick_schedules(self):
        from .scheduler import next_run
        now=time.time()
        for task in self.store.list_tasks():
            s=task.get('schedule')
            if not s or s.get('enabled') is False or not s.get('next_at') or s['next_at']>now:continue
            try:
                self.runner.start(task,s.get('values',{}));s.pop('error',None)
            except Exception as e:s['error']=str(e)
            s['last_at']=now;s['next_at']=next_run(s,now)
            self.store.save_task(task)

    def poll(self):
        if self.closing:return
        try:
            for _ in range(500):
                try:event=self.runner.events.get_nowait()
                except queue.Empty:break
                if event.get('type')=='run':self.notice.set('Run '+str(event.get('status','updated')).replace('_',' '))
            self.refresh_run()
            self.tick_schedules()
        except Exception as e:self.notice.set('Workspace error: '+str(e))
        self.root.after(350,self.poll)

    def close(self):
        if self.runner.active and not messagebox.askyesno('Stop active runs?','Closing stops active processes and pauses schedules. Close now?',parent=self.root):return
        self.closing=True
        self.runner.shutdown()
        self.store.close()
        self.root.destroy()


def main():
    from .instance import WorkspaceLock
    parser=argparse.ArgumentParser(description='Runloom Desk local automation workbench')
    parser.add_argument('--data-dir',type=Path,default=WORKSPACE_ROOT/'.runloom-data')
    args=parser.parse_args()
    root=tk.Tk()
    try:
        lock=WorkspaceLock(args.data_dir.resolve())
    except RuntimeError as e:
        root.withdraw();messagebox.showerror('Workspace already open',str(e));root.destroy();return
    except OSError as e:
        root.withdraw();messagebox.showerror('Cannot open workspace',str(e));root.destroy();return
    try:
        App(root,args.data_dir.resolve())
        root.mainloop()
    except Exception as e:
        root.withdraw()
        messagebox.showerror('Cannot open Runloom Desk',str(e),parent=root)
        root.destroy()
    finally:
        lock.close()
