"""Theme-driven vector itinerary artwork. Uses event facts, never event photos."""
from html import escape
import math
import re
import textwrap


def theme_for(text):
    if re.search(r'\b(ai|artificial intelligence|science|scientific|research|physics|robotics|technology|machine learning|astronomy)\b',text,re.I):
        return 'AI & SCIENCE', '#122858','#654ce5','#60ddd2','science'
    if re.search(r'\b(music|jazz|concert|vinyl|orchestra|opera|comedy|theatre)\b',text,re.I):
        return 'CULTURE & SOUND','#40254f','#b657a6','#ffce87','culture'
    if re.search(r'\b(nature|hike|outdoor|park|forest|garden)\b',text,re.I):
        return 'OUTSIDE & EXPLORING','#18493f','#328377','#e8d893','nature'
    return 'A LITTLE ADVENTURE','#343361','#8562c6','#f0b37f','explore'


def schedule_svg(title,items,theme_text=''):
    label,ink,accent,glow,kind=theme_for(theme_text+' '+title)
    n=min(8,len(items));height=540+n*156
    def txt(x,y,value,size=24,fill='#263139',weight=400):
        return '<text x="%s" y="%s" fill="%s" font-size="%s" font-weight="%s">%s</text>'%(x,y,fill,size,weight,escape(str(value)))
    art=['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="%s" viewBox="0 0 1400 %s"><defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient><linearGradient id="a"><stop stop-color="%s"/><stop offset="1" stop-color="#f8f4fd"/></linearGradient></defs><rect width="1400" height="%s" fill="#f5f1fc"/><rect width="1400" height="440" fill="url(#bg)"/><g font-family="DejaVu Sans, sans-serif">'%(height,height,ink,accent,glow,height)]
    art+=[txt(74,75,'SOLA / YOUR PERSONAL FIELD NOTES',18,'#ffffff',600),txt(74,130,label,20,glow,600)]
    for i,line in enumerate(textwrap.wrap(title,29)[:2]):art.append(txt(70,215+i*58,line,46,'#ffffff',600))
    art.append(txt(74,370,str(n)+' stops. One curious journey.',22,'#ece8f7'))
    # An event-theme illustration: atoms/circuit network, sound waves, or trail.
    if kind=='science':
        art.append('<g transform="translate(1080 220)" fill="none" stroke="%s" stroke-width="3" opacity=".8">'%glow)
        for angle in (0,60,120):art.append('<ellipse rx="190" ry="65" transform="rotate(%s)"/>'%angle)
        art+=['<circle r="32" fill="#ffffff" stroke="none"/><circle cx="180" cy="-20" r="12" fill="#ffffff"/><circle cx="-80" cy="-140" r="11" fill="#ffce87"/></g>']
        for i in range(6):
            x=830+(i%3)*110;y=95+(i//3)*230
            art.append('<path d="M%s %s h40 v40 h35" fill="none" stroke="#ffffff" opacity=".25"/><circle cx="%s" cy="%s" r="6" fill="%s"/>'%(x,y,x,y,glow))
    elif kind=='culture':
        for i in range(18):
            h=50+abs(math.sin(i*.65))*155
            art.append('<rect x="%s" y="%s" width="15" height="%s" rx="8" fill="%s" opacity=".7"/>'%(810+i*25,225-h/2,h,glow))
        art.append(txt(870,355,'LISTEN / DISCOVER / BELONG',15,'#ffffff'))
    else:
        art.append('<path d="M830 350 Q900 70 1080 240 T1340 110" fill="none" stroke="%s" stroke-width="6" stroke-dasharray="12 14"/>'%glow)
        for x,y in [(840,320),(970,180),(1120,240),(1320,130)]:art.append('<circle cx="%s" cy="%s" r="23" fill="#ffffff"/><circle cx="%s" cy="%s" r="8" fill="%s"/>'%(x,y,x,y,accent))
    art.append(txt(74,495,'YOUR TIMETABLE',21,ink,600))
    for i,item in enumerate(items[:8]):
        y=525+i*156
        color=['#ece7fa','#e3f3ef','#fff0dc'][i%3]
        art.append('<rect x="70" y="%s" width="1260" height="136" rx="22" fill="%s"/><circle cx="126" cy="%s" r="26" fill="%s"/>'%(y,color,y+43,accent))
        art.append(txt(117,y+51,str(i+1),22,'#ffffff',600))
        art.append(txt(172,y+36,str(item.get('time') or 'Time to confirm')[:90],18,accent,600))
        for j,line in enumerate(textwrap.wrap(str(item.get('title') or ''),74)[:2]):art.append(txt(172,y+72+j*30,line,25,ink,600))
        art.append(txt(172,y+119,str(item.get('where') or 'Place / price to confirm')[:105],17,'#5b6574'))
    art.append(txt(74,height-24,'Made with Sola + Cloudinary / Source facts, illustrated theme. Review timings and tickets before travel.',15,'#66677c'))
    return ''.join(art)+'</g></svg>',label
