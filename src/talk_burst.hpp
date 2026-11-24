// Timing and SDK frame accounting for one microphone activation.
#pragma once
#include <cstdint>

class TalkBurst {
public:
    static constexpr unsigned duration_ms=5000;
    static constexpr unsigned max_blocks=duration_ms/20;

    void start(std::uint64_t now) { deadline_=now+duration_ms; }
    bool started() const {return deadline_!=0;}
    unsigned seconds_left(std::uint64_t now) const {
        return now>=deadline_ ? 0 : static_cast<unsigned>((deadline_-now+999)/1000);
    }
    bool wants_block() const { return submitted_<max_blocks; }
    bool submitted(int rc) {
        // AudioEncoder::sendFrame returns -2 when its pending PCM cannot
        // supply another encoder frame. Continue with the next input block.
        if(rc<0 && rc!=-2)return false;
        if(rc==-2)++drained_;
        ++submitted_;
        return true;
    }
    unsigned blocks() const {return submitted_;}
    unsigned drained() const {return drained_;}
    std::uint64_t elapsed_ms(std::uint64_t now) const {return now-(deadline_-duration_ms);}
private:
    std::uint64_t deadline_=0;
    unsigned submitted_=0, drained_=0;
};
