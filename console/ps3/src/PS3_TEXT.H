#ifndef ELMA_PS3_TEXT_H
#define ELMA_PS3_TEXT_H
#include <cstring>
#include <cctype>
// direction: +1/-1 cycle last character; +2 append; -2 remove.
inline bool ps3_edit_text(char* text,int maximum,int direction,bool spaces) {
    if(direction!=1 && direction!=-1 && direction!=2 && direction!=-2)return false;
    const char* alphabet=spaces ? "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,-" : "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    const int count=(int)std::strlen(alphabet);
    int length=(int)std::strlen(text);
    if(direction==-2) {if(length)text[length-1]=0;return true;}
    if(direction==2 || !length) {
        if(length<maximum) {text[length]='A';text[length+1]=0;}
        return true;
    }
    if(direction!=1 && direction!=-1)return false;
    const char* found=std::strchr(alphabet,std::toupper((unsigned char)text[length-1]));
    int index=found ? (int)(found-alphabet) : 0;
    text[length-1]=alphabet[(index+direction+count)%count];
    return true;
}
void ps3_text_input(bool enabled);
class Ps3TextInputScope {
public:
    Ps3TextInputScope() {ps3_text_input(true);}
    ~Ps3TextInputScope() {ps3_text_input(false);}
private:
    Ps3TextInputScope(const Ps3TextInputScope&);
    Ps3TextInputScope& operator=(const Ps3TextInputScope&);
};
#endif
