"""Theme-aware controls and line icons, drawn at the display scale of Tk."""
import tkinter as tk
from tkinter import font

PALETTES = {
    'escuro': dict(bg='#191a20', side='#212228', panel='#292a32', field='#22232b',
                   control='#35363f', hover='#40424e', active='#494858', text='#f2f1f5',
                   muted='#b7b6c5', line='#3c3d48', accent='#bfb3ff', ink='#262035',
                   live='#84d8b0', lamp='#ffda80', danger='#ffaba6', black='#131418'),
    'claro': dict(bg='#f3f3f6', side='#e9e9ef', panel='#ffffff', field='#f4f4f8',
                   control='#f9f9fc', hover='#ffffff', active='#e7e2fc', text='#23232d',
                   muted='#575665', line='#d6d6df', accent='#6651a5', ink='#ffffff',
                   live='#21774e', lamp='#9d6600', danger='#a33e44', black='#171820'),
}


def typeface(root):
    families = set(font.families(root))
    return next((s for s in ('Inter','Segoe UI','Arial') if s in families), 'TkDefaultFont')


def icon(c, name, x, y, color):
    def line(*p, **kw):
        pts=[v+(x if i%2==0 else y) for i,v in enumerate(p)]
        c.create_line(*pts,fill=color,width=1.7,capstyle='round',joinstyle='round',**kw)
    def oval(a,b,d,e,fill=''):
        c.create_oval(x+a,y+b,x+d,y+e,outline=color,width=1.7,fill=fill)
    def rect(a,b,d,e):
        c.create_rectangle(x+a,y+b,x+d,y+e,outline=color,width=1.6)
    if name=='bulb':
        oval(-5,-8,5,2);line(-3,2,-2,5,2,5,3,2);line(-2,8,2,8)
    elif name=='sun':
        oval(-4,-4,4,4)
        for a,b in ((0,8),(0,-8),(8,0),(-8,0),(6,6),(-6,6),(6,-6),(-6,-6)):
            line(a*.73,b*.73,a,b)
    elif name=='speaker':
        line(-8,-3,-4,-3,1,-7,1,7,-4,3,-8,3,-8,-3);line(4,-4,6,-2,6,2,4,4)
    elif name=='mic':
        oval(-3,-8,3,2);line(-6,-1,-6,2,-3,5,3,5,6,2,6,-1);line(0,5,0,8);line(-3,8,3,8)
    elif name=='alert':
        line(-8,6,-5,4,-5,-1,-3,-5,0,-6,3,-5,5,-1,5,4,8,6,-8,6);line(-2,8,2,8)
    elif name=='camera':
        rect(-8,-5,3,5);line(3,-2,8,-5,8,5,3,2)
    elif name=='settings':
        for h,knob in [(-5,2),(0,-3),(5,3)]:
            line(-8,h,knob-2,h);line(knob+2,h,8,h);oval(knob-2,h-2,knob+2,h+2)
    elif name=='record':oval(-6,-6,6,6);oval(-2,-2,2,2,color)
    elif name=='folder':line(-8,-5,-3,-5,-1,-3,8,-3,7,6,-8,6,-8,-5)
    elif name=='logout':line(0,-6,-7,-6,-7,6,0,6);line(-2,0,8,0,4,-4);line(8,0,4,4)
    elif name=='play':line(-4,-6,6,0,-4,6,-4,-6)
    elif name=='check':line(-6,0,-2,4,6,-5)
    elif name=='audio':line(-3,4,-3,-5,6,-7,6,2);oval(-7,3,-2,7);oval(2,1,7,5)
    elif name in ('up','down','left','right'):
        dx,dy={'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0)}[name]
        line(-6*dx,-6*dy,6*dx,6*dy);line(4*dy,-4*dx,6*dx,6*dy,-4*dy,4*dx)


class Tile(tk.Canvas):
    def __init__(self, parent, ui, text, command, glyph=None, *, kind='button', role='panel', height=38, width=130):
        super().__init__(parent, height=height, width=width,highlightthickness=0,bd=0,takefocus=1)
        self.ui,self.text,self.action,self.glyph=ui,text,command,glyph
        self.kind,self.role=kind,role
        self.enabled=True;self.selected=False;self.over=False
        self.bind('<Configure>',self.draw)
        for seq, f in [('<Enter>',lambda e:self.hover(True)),('<Leave>',lambda e:self.hover(False)),
                       ('<FocusIn>',self.draw),('<FocusOut>',self.draw),
                       ('<Button-1>',lambda e:self.invoke()),('<Return>',lambda e:self.invoke()),('<space>',lambda e:self.invoke())]:
            self.bind(seq,f)
        ui.tiles.append(self)

    def invoke(self):
        if self.enabled:self.action()

    def hover(self,v):
        self.over=v;self.draw()

    def draw(self,*args):
        p=self.ui.p
        self.delete('all');w=self.winfo_width();h=self.winfo_height()
        self.configure(bg=p[self.role],cursor='hand2' if self.enabled else 'arrow',takefocus=int(self.enabled))
        bg=p['control']
        if self.kind=='nav' and not self.selected:bg=p[self.role]
        if self.over and self.enabled:bg=p['hover']
        if self.selected:bg=p['active']
        if self.kind=='primary' and self.enabled:bg=p['accent']
        fg=p['ink'] if self.kind=='primary' and self.enabled else p['text'] if self.enabled else p['muted']
        if not self.enabled:bg=p[self.role]
        border=p['accent'] if str(self.tk.call('focus'))==str(self) else (p['line'] if self.kind!='nav' and self.enabled else bg)
        r=9
        self.create_polygon(1,r,1,1,r,1,w-r,1,w-1,1,w-1,r,w-1,h-r,w-1,h-1,w-r,h-1,r,h-1,1,h-1,1,h-r,
                            smooth=True,fill=bg,outline=border)
        if self.glyph:
            col=(p['lamp'] if self.glyph=='bulb' else p['danger'] if self.glyph=='alert' else p['accent']) if self.selected else fg
            icon(self,self.glyph,20 if self.text else w/2,h/2,col)
        if self.text:
            self.create_text(39 if self.glyph else w/2,h/2,text=self.text,fill=fg,anchor='w' if self.glyph else 'center',
                             font=(self.ui.face,10,'bold' if self.selected or self.kind=='primary' else 'normal'))

    def state(self,*,text=None,active=None,enabled=None):
        if text is not None:self.text=text
        if active is not None:self.selected=active
        if enabled is not None:self.enabled=enabled
        self.draw()
