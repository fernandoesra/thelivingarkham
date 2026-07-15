# -*- coding: utf-8 -*-
"""Render each Arkham game-icon glyph from the PDF to a trimmed, recolourable
alpha-mask PNG (white glyph on transparent alpha). Also emits a contact sheet
and a manifest. The masks are used in CSS via `-webkit-mask-image` so the app
can tint them (gold / parchment) to match the theme."""
import fitz, numpy as np, json, os, base64, sys
from PIL import Image

ICON_MAP = {
    0xF250:'willpower', 0xF251:'agility', 0xF252:'intellect', 0xF253:'combat', 0xF26C:'wild',
    0xF254:'rogue', 0xF255:'survivor', 0xF256:'guardian', 0xF257:'mystic', 0xF258:'seeker',
    0xF259:'action', 0xF25A:'free', 0xF26D:'reaction',
    0xF25B:'skull', 0xF25C:'cultist', 0xF25D:'autofail', 0xF25E:'elderthing',
    0xF25F:'eldersign', 0xF260:'tablet', 0xF261:'unique', 0xF263:'perinvestigator',
    0xF278:'codex',
}
# Spanish / English display labels for tooltips
LABELS = {
 'willpower':('Voluntad','Willpower'),'agility':('Agilidad','Agility'),
 'intellect':('Intelecto','Intellect'),'combat':('Combate','Combat'),'wild':('Comodín','Wild'),
 'guardian':('Guardián','Guardian'),'seeker':('Buscador','Seeker'),'mystic':('Místico','Mystic'),
 'rogue':('Rebelde','Rogue'),'survivor':('Superviviente','Survivor'),
 'action':('Acción','Action'),'free':('Activación libre','Free trigger'),
 'reaction':('Reacción','Reaction'),'skull':('Cráneo','Skull'),'cultist':('Sectario','Cultist'),
 'autofail':('Fracaso automático','Auto-fail'),'elderthing':('Antiguo','Elder Thing'),
 'eldersign':('Símbolo arcano','Elder Sign'),'tablet':('Tablilla','Tablet'),
 'unique':('Única','Unique'),'perinvestigator':('Por investigador','Per investigator'),
 'codex':('El códice','Codex'),
}

def best_instances(doc):
    best = {}
    for pno in range(doc.page_count):
        for b in doc[pno].get_text('dict')['blocks']:
            if b['type'] != 0: continue
            for l in b['lines']:
                for s in l['spans']:
                    if 'ArkhamHorror' not in s['font']: continue
                    if len(s['text']) != 1: continue          # clean single-glyph spans only
                    cp = ord(s['text'])
                    if cp not in ICON_MAP: continue
                    h = s['bbox'][3]-s['bbox'][1]
                    if cp not in best or h > best[cp][0]:
                        best[cp] = (h, pno, fitz.Rect(s['bbox']))
    return best

def render_mask(page, rect, zoom=16, pad=1.5):
    r = fitz.Rect(rect.x0-pad, rect.y0-pad, rect.x1+pad, rect.y1+pad)
    pm = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=r, alpha=False)
    a = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.h, pm.w, pm.n)[:, :, :3].astype(float)
    lum = 0.299*a[:,:,0] + 0.587*a[:,:,1] + 0.114*a[:,:,2]
    # background = brightest region; map darkness -> alpha
    hi, lo = 175.0, 60.0                     # >=hi transparent, <=lo opaque
    alpha = np.clip((hi - lum) / (hi - lo), 0, 1)
    alpha = (alpha**0.9 * 255).astype(np.uint8)
    # trim to content
    ys, xs = np.where(alpha > 20)
    if len(xs) == 0: return None
    m = int(2*zoom*0.15)
    y0,y1 = max(ys.min()-m,0), min(ys.max()+m+1, alpha.shape[0])
    x0,x1 = max(xs.min()-m,0), min(xs.max()+m+1, alpha.shape[1])
    alpha = alpha[y0:y1, x0:x1]
    rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    rgba[:,:,0]=rgba[:,:,1]=rgba[:,:,2]=255   # white glyph; recolour via CSS mask
    rgba[:,:,3]=alpha
    return Image.fromarray(rgba, 'RGBA')

def main(pdf, outdir):
    os.makedirs(outdir, exist_ok=True)
    doc = fitz.open(pdf)
    best = best_instances(doc)
    manifest = {}
    imgs = {}
    for cp, name in ICON_MAP.items():
        if cp not in best:
            print('MISSING', name); continue
        h, pno, rect = best[cp]
        im = render_mask(doc[pno], rect)
        if im is None:
            print('EMPTY', name); continue
        # cap size for weight
        if im.height > 256:
            w = int(im.width*256/im.height); im = im.resize((max(w,1),256), Image.LANCZOS)
        path = os.path.join(outdir, name+'.png')
        im.save(path)
        imgs[name] = im
        es,en = LABELS[name]
        manifest[name] = {'cp':'%04X'%cp,'es':es,'en':en}   # light manifest (app fetches this)
    json.dump(manifest, open(os.path.join(outdir,'icons.json'),'w',encoding='utf-8'), ensure_ascii=False)
    # contact sheet (dark bg, gold-tinted) for visual QA
    names=list(imgs); cols=6; rows=(len(names)+cols-1)//cols; cell=120
    sheet=Image.new('RGBA',(cols*cell,rows*cell),(30,34,42,255))
    for i,nm in enumerate(names):
        im=imgs[nm].copy()
        s=min((cell-36)/im.width,(cell-36)/im.height); im=im.resize((max(int(im.width*s),1),max(int(im.height*s),1)),Image.LANCZOS)
        gold=Image.new('RGBA',im.size,(212,175,55,255)); gold.putalpha(im.split()[3])
        cx=i%cols*cell+(cell-im.width)//2; cy=i//cols*cell+(cell-im.height)//2-6
        sheet.alpha_composite(gold,(cx,cy))
    sheet.save(os.path.join(outdir,'_contact_sheet.png'))
    print('icons written:', len(manifest), '->', outdir)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
