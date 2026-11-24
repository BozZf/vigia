#include "../src/talk_burst.hpp"
#include <cassert>
#include <cstring>
#include "../src/loop_audio.hpp"

int main(int argc,char** argv) {
    auto clip=argc==2?fopen(argv[1],"w+b"):tmpfile();assert(clip);
    char block[8]{};
    assert(!read_looped_pcm(clip,block,8));
    assert(fwrite("ABCDEF",1,6,clip)==6);rewind(clip);
    assert(read_looped_pcm(clip,block,8) && memcmp(block,"ABCDEFAB",8)==0);
    assert(read_looped_pcm(clip,block,8) && memcmp(block,"CDEFABCD",8)==0);
    fclose(clip);
    TalkBurst burst;
    // Waiting for the SDK to request capture consumes none of the talk time.
    assert(burst.seconds_left(12000)==0);
    burst.start(12000);
    assert(burst.seconds_left(12000)==5);
    for(unsigned i=0;i<250;++i) {
        const auto now=12000+i*20;
        assert(burst.seconds_left(now)==5-i/50);
        assert(burst.wants_block());
        assert(burst.submitted(-2));
    }
    assert(!burst.wants_block() && burst.blocks()==250 && burst.drained()==250);
    assert(burst.seconds_left(16999)==1 && burst.seconds_left(17000)==0);
    assert(burst.elapsed_ms(17000)==5000);

    TalkBurst next;
    next.start(20000);
    assert(next.submitted(0) && next.submitted(-2) && next.submitted(0));
    assert(!next.submitted(-1) && !next.submitted(-11));
    assert(next.blocks()==3 && next.drained()==1 && next.seconds_left(20060)==5);
}
