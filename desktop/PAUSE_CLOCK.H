#ifndef ELMA_PAUSE_CLOCK_H
#define ELMA_PAUSE_CLOCK_H
// Clock is a std::chrono-compatible clock. Supplying time points makes pause
// bookkeeping testable without sleeping or depending on the renderer/input.
template<class Clock> class elma_pause_clock {
    typename Clock::time_point start_,pause_start_;
    bool paused_;
public:
    elma_pause_clock():paused_(false){}
    bool paused()const{return paused_;}
    void reset(typename Clock::time_point now){start_=now;pause_start_=now;paused_=false;}
    void pause(bool value,typename Clock::time_point now){
        if(value && !paused_)pause_start_=now;
        if(!value && paused_)start_+=now-pause_start_;
        paused_=value;
    }
    typename Clock::duration elapsed(typename Clock::time_point now)const{
        return (paused_?pause_start_:now)-start_;
    }
};
#endif
