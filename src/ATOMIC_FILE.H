#ifndef ELMA_ATOMIC_FILE_H
#define ELMA_ATOMIC_FILE_H
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <sys/stat.h>
#ifndef ELMA_ATOMIC_RENAME
#define ELMA_ATOMIC_RENAME rename
#endif
inline bool elma_saved_regular_file(const char* path){
    FILE* f=fopen(path,"rb");if(!f)return false;
    struct stat info;bool regular=fstat(fileno(f),&info)==0 && S_ISREG(info.st_mode);
    fclose(f);return regular;
}
// PS3 cannot rename over an existing destination. A crash between the two
// renames leaves the last complete save in .bak; restore it before reading.
inline bool elma_restore_save(const char* path){
    if(elma_saved_regular_file(path))return true;
    char backup[1024];size_t n=strlen(path);if(n+5>=sizeof(backup))return false;
    memcpy(backup,path,n);memcpy(backup+n,".bak",5);
    return !elma_saved_regular_file(backup) || ELMA_ATOMIC_RENAME(backup,path)==0;
}
// Sibling temporary plus a checked close preserves the old save on failure.
class elma_atomic_file {
    FILE* stream;
    char destination[1024],temporary[1024],backup[1024];
    bool pending;
    int error_;
public:
    explicit elma_atomic_file(const char* path):stream(NULL),pending(false),error_(0){
        destination[0]=temporary[0]=backup[0]=0;
        size_t n=strlen(path);if(n+5>=sizeof(temporary)){error_=ENAMETOOLONG;return;}
        memcpy(destination,path,n+1);memcpy(temporary,path,n);memcpy(temporary+n,".tmp",5);
        memcpy(backup,path,n);memcpy(backup+n,".bak",5);
        if(!elma_restore_save(path)){error_=errno;return;}
        stream=fopen(temporary,"wb");pending=stream!=NULL;if(!stream)error_=errno;
    }
    FILE* file()const{return stream;}
    int error()const{return error_;}
    bool commit(bool payload_ok=true){
        if(!stream)return false;
        bool ok=payload_ok && !ferror(stream);if(!ok)error_=errno?errno:EIO;
        if(fflush(stream)!=0){ok=false;if(!error_)error_=errno?errno:EIO;}
        if(fclose(stream)!=0){ok=false;if(!error_)error_=errno?errno:EIO;}
        stream=NULL;
        if(ok){
            if(ELMA_ATOMIC_RENAME(temporary,destination)==0){pending=false;return true;}
            error_=errno;
#if defined(ELMA_PS3) || defined(ELMA_ATOMIC_TEST_NO_REPLACE)
            if(elma_saved_regular_file(destination)){
                // A stale backup may only be removed while the primary is
                // still complete. Never unlink the destination to replace it.
                remove(backup);
                if(ELMA_ATOMIC_RENAME(destination,backup)==0){
                    if(ELMA_ATOMIC_RENAME(temporary,destination)==0){
                        remove(backup);pending=false;error_=0;return true;
                    }
                    error_=errno;
                    // If rollback itself fails, keep .bak for startup recovery.
                    ELMA_ATOMIC_RENAME(backup,destination);
                }else error_=errno;
            }
#endif
        }
        remove(temporary);pending=false;return false;
    }
    ~elma_atomic_file(){if(stream)fclose(stream);if(pending)remove(temporary);}
private:
    elma_atomic_file(const elma_atomic_file&);
    elma_atomic_file& operator=(const elma_atomic_file&);
};
#ifdef ELMA_PS3
#include <dirent.h>
#include <unistd.h>
#include <cctype>
// Recover only files matching the explicit save extension, never arbitrary backups.
inline void elma_restore_save_directory(const char* directory,const char* extension){
    char root[1024]={};
    if(directory[0]=='/')snprintf(root,sizeof(root),"%s",directory);
    else {char cwd[1024]={};if(!getcwd(cwd,sizeof(cwd)))return;
        if(snprintf(root,sizeof(root),"%s/%s",cwd,directory)>=int(sizeof(root)))return;}
    DIR* dir=opendir(root);if(!dir)return;dirent* item;
    char suffix[32];if(snprintf(suffix,sizeof(suffix),"%s.bak",extension)>=int(sizeof(suffix))){closedir(dir);return;}
    const size_t suffix_size=strlen(suffix);
    while((item=readdir(dir))!=NULL){size_t n=strlen(item->d_name);if(n<suffix_size)continue;
        bool match=true;
        for(size_t i=0;i<suffix_size;++i)if(std::tolower(static_cast<unsigned char>(item->d_name[n-suffix_size+i]))!=suffix[i])match=false;
        if(!match)continue;char path[1024];
        if(snprintf(path,sizeof(path),"%s/%.*s",root,int(n-4),item->d_name)>=int(sizeof(path)))continue;
        elma_restore_save(path);
    }closedir(dir);
}
inline void elma_restore_replay_directory(const char* directory){elma_restore_save_directory(directory,".rec");}
#endif
#endif
