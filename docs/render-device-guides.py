"""Generate editable SVG guides. Render PNGs with render-device-guides.cjs."""
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parent / 'images'
COLORS = ['#1266d6', '#167c5a', '#a44919', '#8a43c6', '#176c7d', '#c02e4e']

def text(x,y,value,size=28,color='#243448',weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{escape(value)}</text>'

def image(name,x,y,w,h):
    return f'<image href="{name}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="none"/>'

def save(name,parts,w,h,title):
    source=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><title>{escape(title)}</title><desc>實機截圖與去背機身的操作圖解。所有標註均為本專案監控功能。</desc><style>text{{font-family:"Noto Sans CJK TC",sans-serif}}</style><rect width="100%" height="100%" fill="#f7f9fc"/>'+''.join(parts)+'</svg>'
    (ROOT/(name+'.svg')).write_text(source)

def badge(x,y,n,color):
    return f'<circle cx="{x}" cy="{y}" r="23" fill="{color}" stroke="white" stroke-width="3"/>'+text(x-8,y+9,str(n),27,'white',700)

def controls(kind):
    r36=kind=='r36';title='R36 MAX 2' if r36 else 'TrimUI Smart Pro S'
    parts=[text(50,67,title+'｜監控按鍵圖',42,weight=700),text(50,115,'進入 Hardware Monitor 後，依圖上的編號操作。',26)]
    if r36:
        x,y,w,h=430,160,640,696
        parts.append(image('r36max2-cutout.png',x,y,w,h))
        positions=[[(.352,.85),(.322,.676),(.714,.851)],[(.789,.674)],[(.735,.729)],[(.519,.794)],[(.594,.735)],[(.444,.734)]]
        screen=(x+.195*w,y+.055*h,.645*w,.49*h)
        labels=[('方向鍵／搖桿','方向鍵／左：導覽；右：90° 旋轉'),('A｜開啟詳細頁','再按一次，查看選定資訊卡'),('B｜返回','單項頁 → 詳細頁 → 總覽'),('FN｜關屏／喚醒','再按一次恢復；MQTT 持續接收'),('Start｜輪播','在總覽暫停或恢復輪播'),('Select + B｜退出','同時按住，回到遊戲選單')]
        offsets=[(-34,30),(40,-18),(38,20),(-40,10),(40,-8),(-40,-12)]
    else:
        x,y,w,h=105,220,1290,486
        parts.append(image('trimui-smart-pro-s-cutout.png',x,y,w,h))
        positions=[[(.11,.35),(.125,.67),(.875,.67)],[(.916,.35)],[(.88,.44)],[(.881,.255)],[(.884,.85)],[(.839,.85)]]
        screen=(x+.204*w,y+.12*h,.59*w,.76*h)
        labels=[('方向鍵／搖桿','方向鍵／左：導覽；右：90° 旋轉'),('A｜開啟詳細頁','再按一次，查看選定資訊卡'),('B｜返回','單項頁 → 詳細頁 → 總覽'),('X｜關屏／喚醒','再按 X 恢復；MQTT 持續接收'),('Start｜輪播','在總覽暫停或恢復輪播'),('Select + Start｜退出','同時按住，回到原廠選單')]
        offsets=[(-35,-26),(36,-10),(34,24),(15,-40),(28,35),(-28,35)]
    if not r36:
        for label,px in [('L／L1',.17),('R／R1',.83)]:
            ax=x+px*w
            parts.extend([text(ax-55,187,label+' 肩鍵',26,weight=700),f'<path d="M{ax},198 V{y+15}" stroke="#47627c" stroke-width="4"/><circle cx="{ax}" cy="{y+15}" r="9" fill="#47627c"/>'])
    sx,sy,sw,sh=screen
    parts.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" fill="#101825"/>')
    parts.append(image('r36-dashboard.png' if r36 else 'trimui-dashboard.png',sx,sy,sw,sh))
    for n,points in enumerate(positions,1):
        for px,py in points:
            ax,ay=x+px*w,y+py*h;dx,dy=offsets[n-1];color=COLORS[n-1]
            parts.append(f'<circle cx="{ax}" cy="{ay}" r="24" fill="none" stroke="{color}" stroke-width="5"/><path d="M{ax},{ay} l{dx},{dy}" stroke="{color}" stroke-width="3"/>')
            parts.append(badge(ax+dx,ay+dy,n,color))
    top=900 if r36 else 790
    for i,(heading,detail) in enumerate(labels):
        cx=55+(i%2)*725;cy=top+(i//2)*108
        parts.append(f'<rect x="{cx}" y="{cy-34}" width="670" height="96" rx="14" fill="white" stroke="#d6deea"/>')
        parts.extend([badge(cx+35,cy+6,i+1,COLORS[i]),text(cx+75,cy+2,heading,29,weight=700),text(cx+75,cy+39,detail,24)])
    bottom=top+350
    parts.extend([text(55,bottom,'L1／R1（上緣／機背肩鍵）：總覽翻頁；詳細頁切換上一台／下一台。',26,weight=700),text(55,bottom+44,'機身為商品照片去背示意，螢幕嵌入實機截圖；不代表原廠內建此功能。',23,'#607085')])
    save(kind+'-controls',parts,1500,bottom+80,title+'按鍵操作')

def entry(kind):
    r36=kind=='r36';title='R36 MAX 2' if r36 else 'TrimUI Smart Pro S'
    shots=['r36-system-ports.png','r36-port-monitor.png','r36-dashboard.png'] if r36 else ['trimui-apps-tab.png','trimui-app-monitor.png','trimui-dashboard.png']
    headings=['在遊戲機系統選單選 PORTS','選笑臉晶片 Hardware Monitor','進入監控總覽'] if r36 else ['用上緣 L／R 切到「應用」Apps','選笑臉晶片 Hardware Monitor','進入監控總覽']
    instructions=['左右選 PORTS，按 A','方向鍵選圖示，再按 A','方向鍵選電腦，按 A 查看詳細頁'] if r36 else ['先切到原廠「應用」分類，再找監控圖示','方向鍵選圖示，再按 A','方向鍵選電腦，按 A 查看詳細頁']
    row=640 if r36 else 540
    parts=[text(45,64,title+'｜從遊戲選單進入監控',39,weight=700),text(45,109,'先完成安裝。下列選單與監控頁均取自對應實機；機身為去背合成示意。',24)]
    for i,shot in enumerate(shots):
        yy=160+i*row
        parts.extend([badge(70,yy+20,i+1,'#1266d6'),text(110,yy+30,headings[i],32,weight=700)])
        if r36:
            x,y,w,h=80,yy+82,420,457;sx,sy,sw,sh=x+.195*w,y+.055*h,.645*w,.49*h
            parts.append(image('r36max2-cutout.png',x,y,w,h));parts.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" fill="#111"/>');parts.append(image(shot,sx,sy,sw,sh))
            mx,my,mw,mh=610,yy+75,720,540
        else:
            x,y,w,h=35,yy+160,550,207;sx,sy,sw,sh=x+.204*w,y+.12*h,.59*w,.76*h
            parts.append(image('trimui-smart-pro-s-cutout.png',x,y,w,h));parts.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" fill="#111"/>');parts.append(image(shot,sx,sy,sw,sh))
            mx,my,mw,mh=610,yy+75,720,405
        parts.append(image(shot,mx,my,mw,mh))
        if i<2:
            if r36:rx,ry,rw,rh=(.255,.17,.49,.65) if i==0 else (.33,.29,.34,.47)
            else:rx,ry,rw,rh=(.49,.01,.06,.085) if i==0 else (.73,.33,.255,.46)
            parts.append(f'<rect x="{mx+rx*mw}" y="{my+ry*mh}" width="{rw*mw}" height="{rh*mh}" rx="8" fill="none" stroke="#ffdf37" stroke-width="7"/>')
        parts.append(text(45,yy+row-18,instructions[i],27,'#1266d6',700))
    save(kind+'-entry',parts,1400,160+3*row,title+'開啟監控面板')

for kind in ['r36','trimui']:
    controls(kind);entry(kind)
print('Wrote four editable SVG guides')
