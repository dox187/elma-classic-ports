"""Read the native CG Pixel 3x5 bitmap without resizing or antialiasing."""
from pathlib import Path

FONT_PATH = Path(__file__).resolve().parents[1]/'fonts/CG-pixel-3x5-mono.bdf'


def font_rows():
    glyphs = {}
    for block in FONT_PATH.read_text().split('STARTCHAR ')[1:]:
        lines = block.splitlines()
        code = int(next(line for line in lines if line.startswith('ENCODING ')).split()[1])
        if not 32 <= code <= 95:
            continue
        width, height, x, y = map(int, next(line for line in lines if line.startswith('BBX ')).split()[1:])
        assert 0 <= x and x+width <= 3 and 0 <= y and y+height <= 5, (code, width, height, x, y)
        rows = [0]*5
        start = lines.index('BITMAP')+1
        for row, value in enumerate(lines[start:start+height]):
            rows[5-height-y+row] = (int(value, 16) >> (len(value)*4-width)) << (3-width-x)
        glyphs[code] = rows
    assert len(glyphs) == 64
    return [glyphs[code] for code in range(32, 96)]


def pair_tile(left, right, rows):
    left, right = ord(left.upper())-32, ord(right.upper())-32
    assert 0 <= left < 64 and 0 <= right < 64
    bits = [0]+[(a << 5) | (b << 1) for a, b in zip(rows[left], rows[right])]+[0, 0]
    return bytes(value for row in bits for value in (255, row))


def write_header(out, rows):
    # The riding clock changes every presentation. Store its paired glyphs
    # directly, so updating a digit only uploads one existing 16-byte tile.
    clock = [('hud_digit_pairs', [f'{n:02d}' for n in range(100)]),
             ('hud_seconds_tens', [':'+str(n) for n in range(6)]),
             ('hud_seconds_ones', [str(n)+'.' for n in range(10)])]
    (out/'clock_font.h').write_text(
        '/* Native CG Pixel 3x5 clock tiles; generated without resampling. */\n'
        '#ifndef GBC_CLOCK_FONT_H\n#define GBC_CLOCK_FONT_H\n#include <stdint.h>\n'+
        ''.join('static const uint8_t %s[%d][16]={\n%s\n};\n' % (
            name, len(labels), ',\n'.join('    {'+','.join(map(str,pair_tile(*label,rows)))+'}'
                                        for label in labels)) for name,labels in clock)+
        '#endif\n')
    values = ',\n'.join('    {'+','.join(map(str, row))+'}' for row in rows)
    (out/'ui_font.h').write_text('''/* CG Pixel 3x5 Mono by vyznev, CC0; native pixels, four-pixel advance. */
#ifndef GBC_UI_FONT_H
#define GBC_UI_FONT_H
#include <stdint.h>
static const uint8_t ui_font_rows[64][5]={
'''+values+'''
};
static uint8_t ui_font_index(uint8_t c) {
    if(c>='a' && c<='z')c-='a'-'A';
    return c>=32 && c<=95 ? c-32 : 0;
}
static void ui_font_pair(uint8_t left,uint8_t right,uint8_t *tile) {
    const uint8_t *a=ui_font_rows[ui_font_index(left)];
    const uint8_t *b=ui_font_rows[ui_font_index(right)];
    uint8_t row;
    for(row=0;row<8;++row) {
        tile[row*2]=255;
        tile[row*2+1]=(row>=1 && row<=5)?(a[row-1]<<5)|(b[row-1]<<1):0;
    }
}
#endif
''')
