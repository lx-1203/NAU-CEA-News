"""Capture the approved CSS bubble as a real transparent motion layer."""
import math

def capture_bubble(page,path):
    bounds=page.locator('.tv-frame').bounding_box()
    style=page.add_style_tag(content='html,body{background:transparent!important}body *{visibility:hidden!important}.news-side-label,.news-side-label *{visibility:visible!important}')
    try:page.screenshot(path=str(path),clip=bounds,omit_background=True)
    finally:style.evaluate('e=>e.remove()')

def bubble_filter(input_index,start_seconds,width=1920):
    if input_index<1 or not math.isfinite(start_seconds) or start_seconds<0:raise ValueError('气泡时间/输入序号无效')
    amplitude=width*.0038
    return f"[{input_index}:v]format=rgba[bubble];[{{back}}][bubble]overlay=x=0:y='-{amplitude/2:.6f}*(1-cos(2*PI*(t+{start_seconds:.6f})/4.8))':eval=frame[withbubble];"
