"""FH Edge enclosure revision 2. Millimetres. CadQuery 2.7 / OCCT.

Rebuilds from the supplied shell/base STEP, preserves the exterior and screw
pattern. PN5180 geometry is an explicitly labelled envelope, not a vendor CAD.

The FilamentHub mark is taken from the official SVG (source/filamenthub-mark.svg),
never redrawn. make_mark.py turns it into source/filamenthub-mark.brep; when the
brand changes, replace the SVG, run make_mark.py and rebuild.

    uv run --no-project --python 3.12 --with cadquery python build_model.py
"""
from pathlib import Path
import json
import cadquery as cq

ROOT = Path(__file__).resolve().parent
SRC, CAD, STL = (ROOT / p for p in ('source','CAD','STL'))
for p in (CAD,STL): p.mkdir(exist_ok=True)
P = dict(esp_x=-37.6, esp_usb_edge_y=22.8, esp_back_z=5.0,
         pcb_side_clearance=.25, flange_width=1.8, flange_z=2.0,
         flange_thickness=1.6, pn_x=9.4, pn_length=70., pn_width=39.,
         pn_thickness_assumed=1.6, pn_component_face_z=11.0,
         pn_header_height_budget=8.5, pcb_axial_play=.25,
         usb_through_w=10., usb_through_h=4.3, usb_through_r=1.65,
         usb_boot_w=12.2, usb_boot_h=6.8, usb_boot_depth=1.2,
         usb_outer_chamfer=.35, lightpipe_d=2.0, lightpipe_bore=2.3,
         lightpipe_tip_z_PWR=7.315, lightpipe_tip_z_IO8=8.8)

def box(x0,x1,y0,y1,z0,z1):
    return cq.Solid.makeBox(x1-x0,y1-y0,z1-z0,cq.Vector(x0,y0,z0))

def rr(w,h,r,z0,z1,cx=0.,cy=0.):
    return (cq.Workplane('XY').box(w,h,z1-z0,centered=(True,True,False))
            .edges('|Z').fillet(r).val().translate((cx,cy,z0)))

def cyl(r,z0,z1,x=0.,y=0.):
    return cq.Solid.makeCylinder(r,z1-z0,cq.Vector(x,y,z0))

def port(w,h,r,depth,end_y,cx,cz):
    return rr(w,h,r,0,depth).rotate((0,0,0),(1,0,0),90).translate((cx,end_y,cz))

def prism_poly(points,z0,z1):
    return cq.Workplane('XY').polyline(points).close().extrude(z1-z0).val().translate((0,0,z0))

MARK_OUTLINE=SRC/'filamenthub-mark.brep' # written by make_mark.py from the official SVG
MARK_ARC=288.0   # the outer arc's diameter in the SVG's units
MARK_RING_D=30.0 # the same arc on the case: the size of the tap target it replaces
MARK_X,MARK_Y=23.4,0.0 # over the reader's antenna
# Where the other printed parts lie beside the shell in the print set.
PRINT_LID_Y=58.0
PRINT_PIPE_Y=-34.0
PRINT_PIPES=(('PWR',-6.0),('IO8',6.0))

def brand_mark(z0,z1):
    """The official mark as solids over the antenna, scaled as a whole, proportions untouched."""
    outline=cq.Shape.importBrep(str(MARK_OUTLINE)).scale(MARK_RING_D/MARK_ARC)
    solids=[cq.Solid.extrudeLinear(face,cq.Vector(0,0,z1-z0)).translate((MARK_X,MARK_Y,z0))
            for face in outline.Faces()]
    return cq.Compound.makeCompound(solids)

def export(shape,name,print_transform=None,stl=True):
    cq.exporters.export(shape,str(CAD/(name+'.step')))
    shape.exportBrep(str(CAD/(name+'.brep')))
    if stl:
        printed=print_transform(shape) if print_transform else shape
        cq.exporters.export(printed,str(STL/(name+'.stl')),tolerance=.025,angularTolerance=.10)

def main():
    print('Reading source BRep',flush=True)
    shell=cq.importers.importStep(str(SRC/'original-shell.step')).val()
    base=cq.importers.importStep(str(SRC/'original-base.step')).val()
    native_cache=SRC/'esp-native-cache.brep'
    if native_cache.exists():esp_native=cq.Shape.importBrep(str(native_cache))
    else:
        esp_native=cq.importers.importStep(str(SRC/'Esp32-C3_mini.STEP')).val()
        esp_native.exportBrep(str(native_cache))
    # Correct proper rotation: +Y component normal becomes +Z; USB points +Y.
    pcb=esp_native.Solids()[0]; bb=pcb.BoundingBox()
    tx=P['esp_x']-(bb.xmin+bb.xmax)/2
    ty=P['esp_usb_edge_y']+bb.zmin
    tz=P['esp_back_z']-bb.ymin
    esp=esp_native.rotate((0,0,0),(1,0,0),90).translate((tx,ty,tz))
    solids=esp.Solids()
    leds=[]
    for idx in (59,61):
        b=solids[idx].BoundingBox()
        # Centres are identical for package and lens; source optical face =
        # component plane +0.595 mm, independently measured from the model.
        leds.append(((b.xmin+b.xmax)/2,(b.ymin+b.ymax)/2,P['esp_back_z']+1.665))
    usb_z=P['esp_back_z']+2.775
    print('Removing old ESP nest and six inaccurate tall supports',flush=True)
    shell=shell.cut(box(-48.5,-27.3,-2.5,22.75,3.8,14.0))
    # Remove every old electronics post; leave the original 2-mm base intact.
    base=base.cut(box(-49,45,-20,20,2.0,13.0))
    # Restore the old port from a clean outer wall with the original chamfer.
    outer=rr(116,50,8,0,15.2)
    outer=cq.Workplane(obj=outer).faces('>Z').edges().chamfer(1.2).val()
    clean_wall=outer.cut(rr(112,46,6,-.1,14.0))
    shell=shell.fuse(clean_wall.intersect(box(-45.5,-29.7,22.9,25.1,5.0,15.3)))
    shell=shell.fuse(cyl(2.5,14.,14.8,-37.6,7.54))
    # Continuous lid stop. It joins all four original screw bosses.
    ledge=rr(112.4,46.4,6.2,2.,3.6).cut(rr(108.4,42.4,4.2,1.9,3.7))
    w1=cq.Workplane(obj=rr(108.4,42.4,4.2,3.6,3.7)).faces('<Z').val().outerWire()
    w2=cq.Workplane(obj=rr(112.,46.,6.,5.4,5.5)).faces('<Z').val().outerWire()
    slope_void=cq.Solid.makeLoft([w1,w2],ruled=True)
    ledge=ledge.fuse(rr(112.4,46.4,6.2,3.6,5.4).cut(slope_void))
    shell=shell.fuse(ledge)
    # Local roofward relief of the printable slope below the USB-side PCB edge.
    # The full 1.8-mm-wide load-bearing ring at Z2..3.6 stays uninterrupted.
    shell=shell.cut(box(-47.,-28.2,21.,23.,4.7,6.5))
    # Stepped USB port: close clearance at socket; room for the cable boot.
    through=port(10.,4.3,1.65,3.4,25.5,P['esp_x'],usb_z)
    boot=port(12.2,6.8,2.0,1.6,25.4,P['esp_x'],usb_z)
    shell=shell.cut(through).cut(boot).clean()
    # Actual 0.35-mm chamfer of the outer opening, no oversized full-depth slot.
    port_edges=[]
    for e in shell.Edges():
        b=e.BoundingBox()
        if (abs(b.ymin-25)<1e-5 and abs(b.ymax-25)<1e-5
            and b.xmin>P['esp_x']-6.2 and b.xmax<P['esp_x']+6.2
            and b.zmin>usb_z-3.5 and b.zmax<usb_z+3.5):port_edges.append(e)
    if len(port_edges)!=8:raise RuntimeError('Expected 8 outside port edges, got '+str(len(port_edges)))
    shell=shell.chamfer(.35,None,port_edges).clean()

    # Four pads under bare ESP backside, inset from solder/pin rows.
    for x in (-43.2,-32.0):
        for y in (5.8,17.0):
            base=base.fuse(rr(2.4,3.4,.35,2.,5.,x,y))
    # Lateral guidance remains below the component face; no snap on the PCB.
    for x0,x1 in ((-48.05,-46.851),(-28.349,-27.15)):
        for y0,y1 in ((5.0,9.0),(16.0,20.0)):
            base=base.fuse(box(x0,x1,y0,y1,2.,6.0))
    for x in (-43.2,-32.0):base=base.fuse(box(x-1.6,x+1.6,-1.7,-.5,2.,6.0))
    # ESP captured with 0.25-mm axial free play when shell is closed.
    # Narrow pads are intentionally on bare corner margins, away from pin rows.
    esp_press=[]
    press_data=[(-45.1024,22.3283,1.,.8),(-30.1024,22.3283,1.,.8),
                (-45.3824,.7783,1.2,1.2),(-29.8324,.7783,1.2,1.2)]
    for x,y,w,h in press_data:
        q=box(x-w/2,x+w/2,y-h/2,y+h/2,6.32,14.)
        q=q.fuse(box(x-1.,x+1.,y-1.,y+1.,9.8,14.))
        esp_press.append(q);shell=shell.fuse(q)

    # PN5180 holds by bare PCB edges, never by guessed mounting-hole centres.
    # The antenna-side contacts are clear of the entire populated left zone.
    pn_contacts=[]
    for x in (6.,40.):
        for y in (-19.05,19.05):
            # Slightly tapered 9-mm columns; small, well-defined edge contact.
            wp=cq.Workplane('XY',origin=(x,y,2.)).rect(6.,2.6)
            q=wp.workplane(offset=9.).rect(4.,.9).loft(combine=True).val()
            base=base.fuse(q);pn_contacts.append(q)
            shell=shell.fuse(box(x-2,x+2,y-.45,y+.45,12.85,14.))

    # Optical guides. Thick retaining collars end above all ESP components.
    pipes=[]
    for i,(x,y,z) in enumerate(leds):
        shell=shell.fuse(cyl(2.0,9.8,14.,x,y))
        shell=shell.cut(cyl(1.15,9.7,15.3,x,y))
        shell=shell.cut(cyl(1.6,14.65,15.3,x,y))
        tip=z+.65 if i==0 else P['lightpipe_tip_z_IO8']
        pipe=cyl(1.0,tip,14.65,x,y).fuse(cyl(1.4,14.65,15.2,x,y)).clean()
        pipes.append(pipe)
    # The FilamentHub mark is the tap target over the antenna, inlaid 0.4 mm.
    # The supplied shell carries a plain ring and dot there: fill them first.
    old_target=[cyl(15,14.8,15.2,23.4,0).cut(cyl(13.6,14.7,15.3,23.4,0)),cyl(1.6,14.8,15.2,23.4,0)]
    for q in old_target:shell=shell.fuse(q)
    shell=shell.clean()
    nfc=brand_mark(14.8,15.2)
    shell=shell.cut(nfc)

    shell=shell.clean();base=base.clean()
    # No fictitious precision: PN PCB and occupied volume are separate named
    # envelopes. Mounting holes are deliberately not invented from a photo.
    pn_board=box(-25.6,44.4,-19.5,19.5,11.,12.6)
    pn_logic=box(-21.4,-1.0,-17.,17.,8.,11.)
    pn_header=box(-25.0,-22.0,-17.8,17.8,2.5,11.)
    pn_back_solder=box(-25.0,-22.,-17.8,17.8,12.6,13.6)

    print('Exporting separate solids and assembly',flush=True)
    shell_to_print=lambda s:s.rotate((0,0,0),(1,0,0),180).translate((0,0,15.2))
    export(shell,'fh-edge-kit-shell',shell_to_print)
    export(base,'fh-edge-kit-base')
    export(nfc,'fh-edge-kit-mark',shell_to_print)
    # The IO8 pipe is shorter to clear the nearby reset button at all allowed
    # board positions. Two distinct physical parts, one file per part.
    for refpipe,name in zip(pipes,('PWR','IO8')):
        b=refpipe.BoundingBox()
        localpipe=refpipe.translate((-(b.xmin+b.xmax)/2,-(b.ymin+b.ymax)/2,-b.zmin))
        height=b.zmax-b.zmin
        flip=lambda s,h=height:s.rotate((0,0,0),(1,0,0),180).translate((0,0,h))
        export(localpipe,'fh-edge-kit-lightpipe-'+name,flip)
    export(esp,'ESP32-C3-positioned',stl=False)
    export(pn_board,'PN5180-PCB-envelope-ASSUMED',stl=False)
    export(cq.Compound.makeCompound([pn_logic,pn_header,pn_back_solder]),'PN5180-component-keepouts-ASSUMED',stl=False)
    # Remove obsolete duplicate-orientation outputs from previous revisions.
    for pattern in ('PRINT-*.stl','*lightpipe-qty2*','fh-edge-kit-FH-logo.*','*shell-with-mark-PRINT*'):
        for folder in (CAD,STL):
            for old in folder.glob(pattern):old.unlink()
    # A small exact wall sample for checking the chosen physical USB cable.
    coupon=shell.intersect(box(-49.6,-25.6,23.,25.,1.775,13.775)).clean()
    coupon=coupon.rotate((0,0,0),(1,0,0),-90).translate((37.6,-7.775,25))
    cq.exporters.export(coupon,str(CAD/'USB-fit-coupon.step'))
    (STL/'test').mkdir(exist_ok=True)
    cq.exporters.export(coupon,str(STL/'test'/'USB-fit-coupon.stl'),tolerance=.025,angularTolerance=.1)
    asm=cq.Assembly(name='FH_Edge_v2_REVIEW_PN_ENVELOPES')
    for name,shape,color in [
        ('shell',shell,(.06,.18,.20)),('base',base,(.09,.23,.25)),
        ('FilamentHub_mark',nfc,(.08,.85,.85)),
        ('PN5180_PCB_ENVELOPE_ASSUMED',pn_board,(.06,.27,.40)),
        ('PN5180_components_KEEP_OUT_ASSUMED',pn_logic,(.65,.35,.12)),
        ('PN5180_header_KEEP_OUT_ASSUMED',pn_header,(.45,.25,.1)),
        ('PN5180_back_solder_KEEP_OUT_ASSUMED',pn_back_solder,(.65,.4,.1))]:
        asm.add(shape,name=name,color=cq.Color(*color))
    for i,s in enumerate(solids):
        col=(.04,.18,.30) if i==0 else ((.75,.77,.8) if 72<=i<=115 else (.13,.14,.16))
        if i in (59,60):col=(1,.15,.05)
        if i in (61,62):col=(.05,.35,1.)
        if i==116:col=(.75,.24,.09)
        asm.add(s,name=f'ESP_part_{i:03d}',color=cq.Color(*col))
    for i,p in enumerate(pipes):asm.add(p,name=f'lightpipe_{i+1}',color=cq.Color(.75,.9,1.,.55))
    asm.save(str(CAD/'FH-Edge-v2-assembly.step'))
    # One file for the slicer: every printed part as it is printed. The shell
    # lies face down with the mark already in register, as two named parts for
    # two filaments; the lid and the two light pipes lie beside it.
    print_asm=cq.Assembly(name='FH_Edge_v2_print_set')
    print_asm.add(shell_to_print(shell),name='shell',color=cq.Color(.58,.20,.92))
    print_asm.add(shell_to_print(nfc),name='FilamentHub_mark',color=cq.Color(.93,.91,1.))
    print_asm.add(base.translate((0,PRINT_LID_Y,0)),name='lid',color=cq.Color(.09,.07,.18))
    for (name,x),refpipe in zip(PRINT_PIPES,pipes):
        b=refpipe.BoundingBox()
        flat=refpipe.translate((-(b.xmin+b.xmax)/2,-(b.ymin+b.ymax)/2,-b.zmin))
        flat=flat.rotate((0,0,0),(1,0,0),180).translate((x,PRINT_PIPE_Y,b.zmax-b.zmin))
        print_asm.add(flat,name='lightpipe_'+name,color=cq.Color(.75,.9,1.,.55))
    print_asm.save(str(CAD/'FH-Edge-v2-PRINT.step'))
    # Fast exact BRep assets for validation and geometry-derived previews.
    for name,s in [('led_pipe_1',pipes[0]),('led_pipe_2',pipes[1]),('pn_logic',pn_logic),('pn_header',pn_header),('pn_back_solder',pn_back_solder)]:
        s.exportBrep(str(CAD/(name+'.brep')))
    pinfo=dict(P)
    pinfo.update(esp_translation=[tx,ty,tz],led_centres=leds,usb_z=usb_z,
                 esp_board_bbox=[-46.601,-28.599,-.2,22.8,5.,6.07],
                 pn_hole_locations='Not used; actual hole pattern is not corner rectangle',
                 pn_component_model='Envelope only; thickness and connector height require physical confirmation',
                 esp_press_centres_and_sizes=press_data)
    (ROOT/'parameters.json').write_text(json.dumps(pinfo,ensure_ascii=False,indent=2))
    print(json.dumps({'shell_solids':len(shell.Solids()),'shell_valid':shell.isValid(),
                      'mark_solids':len(nfc.Solids()),'mark_bounds':[round(v,3) for v in (
                          nfc.BoundingBox().xmin,nfc.BoundingBox().xmax,
                          nfc.BoundingBox().ymin,nfc.BoundingBox().ymax)],
                      'base_solids':len(base.Solids()),'base_valid':base.isValid(),
                      'LED':leds,'USB_center_z':usb_z},indent=2),flush=True)

if __name__=='__main__':main()
