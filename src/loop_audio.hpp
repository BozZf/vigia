#pragma once
#include <cstdio>
// Fill exactly one output block, including when the loop wraps mid-block.
inline bool read_looped_pcm(FILE* file,char* pcm,size_t size){
    size_t used=0;
    while(used<size){
        auto count=fread(pcm+used,1,size-used,file);
        used+=count;
        if(used==size)return true;
        if(ferror(file) || (!count && ftell(file)<=0) || fseek(file,0,SEEK_SET))return false;
    }
    return true;
}
