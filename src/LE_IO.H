#ifndef ELMA_LE_IO_H
#define ELMA_LE_IO_H
#include <cstdio>
#include <cstddef>
#include <cstring>
#include <cstdint>
#include <type_traits>
#include <vector>
#include <limits>
// All original Elma files are little endian. Never apply this to encrypted
// bytes: decode encryption first, and encode endian before encryption.
inline bool elma_big_endian() { const uint16_t n=1; return !*reinterpret_cast<const unsigned char*>(&n); }
template<class T> inline void elma_swap(T& value) {
    static_assert(std::is_arithmetic<T>::value, "A disk structure needs an explicit field converter");
    unsigned char* p=reinterpret_cast<unsigned char*>(&value);
    for(size_t i=0;i<sizeof(T)/2;++i) { unsigned char c=p[i];p[i]=p[sizeof(T)-1-i];p[sizeof(T)-1-i]=c; }
}
template<class T> inline void elma_convert(T* p,size_t bytes) {
    if(elma_big_endian()) for(size_t i=0;i<bytes/sizeof(T);++i) elma_swap(p[i]);
}
template<class T> inline size_t elma_read(T* p,size_t size,size_t count,FILE* f) {
    if(count && size>std::numeric_limits<size_t>::max()/count)return 0;
    const size_t bytes=size*count;
    if(!bytes) return 0;
    // Legacy callers sometimes read a 32-bit disk integer into an LP64 long.
    if(std::is_integral<T>::value && sizeof(T)>1 && bytes<sizeof(T)) {
        unsigned char raw[sizeof(T)]={}; size_t n=std::fread(raw,1,bytes,f);
        if(elma_big_endian()) for(size_t i=0;i<sizeof(T)/2;++i) { unsigned char c=raw[i];raw[i]=raw[sizeof(T)-1-i];raw[sizeof(T)-1-i]=c; }
        std::memcpy(p,raw,sizeof(T));
        return size ? n/size : 0;
    }
    size_t n=std::fread(p,size,count,f); elma_convert(p,n*size); return n;
}
template<class T> inline size_t elma_write(const T* p,size_t size,size_t count,FILE* f) {
    if(count && size>std::numeric_limits<size_t>::max()/count)return 0;
    size_t bytes=size*count;
    if(!bytes) return 0;
    if(std::is_integral<T>::value && sizeof(T)>1 && bytes<sizeof(T)) {
        unsigned char raw[sizeof(T)]; std::memcpy(raw,p,sizeof(T));
        if(elma_big_endian()) for(size_t i=0;i<sizeof(T)/2;++i) { unsigned char c=raw[i];raw[i]=raw[sizeof(T)-1-i];raw[sizeof(T)-1-i]=c; }
        return size ? std::fwrite(raw,1,bytes,f)/size : 0;
    }
    if(!elma_big_endian()) return std::fwrite(p,size,count,f);
    // Round without addition overflow, and reject impossible object extents.
    if(bytes>static_cast<size_t>(std::numeric_limits<ptrdiff_t>::max()))return 0;
    std::vector<T> copy(bytes/sizeof(T)+(bytes%sizeof(T)!=0));
    std::memcpy(copy.data(),p,bytes); elma_convert(copy.data(),bytes);
    return std::fwrite(copy.data(),size,count,f);
}
#endif
