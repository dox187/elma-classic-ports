#include <chrono>
#include "PAUSE_CLOCK.H"
int main(){
    typedef std::chrono::steady_clock clock;typedef clock::time_point time;
    elma_pause_clock<clock> timer;time zero{};
    timer.reset(zero);timer.pause(true,zero+std::chrono::seconds(1));
    timer.pause(true,zero+std::chrono::seconds(100));
    if(timer.elapsed(zero+std::chrono::hours(1))!=std::chrono::seconds(1))return 1;
    timer.pause(false,zero+std::chrono::hours(1));
    if(timer.elapsed(zero+std::chrono::hours(1)+std::chrono::seconds(2))!=std::chrono::seconds(3))return 2;
    timer.pause(false,zero+std::chrono::hours(1)+std::chrono::seconds(3));
    if(timer.elapsed(zero+std::chrono::hours(1)+std::chrono::seconds(3))!=std::chrono::seconds(4))return 3;
    timer.pause(true,zero+std::chrono::hours(2));timer.reset(zero+std::chrono::hours(3));
    if(timer.elapsed(zero+std::chrono::hours(3)+std::chrono::seconds(1))!=std::chrono::seconds(1))return 4;
    // An XMB/native dialog entered from an already-paused game menu must
    // leave ownership with that menu, so its remaining time stays excluded.
    timer.reset(zero);timer.pause(true,zero+std::chrono::seconds(1));
    const bool nested_owns_pause=!timer.paused();
    if(nested_owns_pause)timer.pause(true,zero+std::chrono::seconds(2));
    if(nested_owns_pause)timer.pause(false,zero+std::chrono::seconds(10));
    if(!timer.paused() || timer.elapsed(zero+std::chrono::seconds(20))!=std::chrono::seconds(1))return 5;
    timer.pause(false,zero+std::chrono::seconds(30));
    if(timer.elapsed(zero+std::chrono::seconds(31))!=std::chrono::seconds(2))return 6;
    return 0;
}
