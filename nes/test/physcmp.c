// Runs the fixed point physics of the NES version next to the double
// precision physics of the game on a level, with the same inputs, and
// prints where the bikes are.
//
//   physcmp LEVEL.txt "G120 N60 GR20 B40 ..." [v]
//
// The level is a text file of lines (count, start, then x y dx dy per line).
// The inputs are steps of: G gas, B brake, R volt right, L volt left,
// T turn around, N nothing, followed by the number of steps. With ONESTEP=n
// in the environment, step n is also taken by both from the same state and
// the changes of the velocities are compared.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/physics.h"
#include "refphys.h"

static rseg Rsegs[4000];
static seg_t Fsegs[8000];
static int32_t Fx[8000], Fy[8000];
static int Nr, Nf;
// Like the grid of the NES: the lines within 0.5 m of the 4 m cell of the
// point, from the cell's corner.
static seg_t Cell[8000];
const seg_t* Seg_cur;
uint8_t Seg_left;
int32_t Seg_ox, Seg_oy;

void seg_query( int32_t x, int32_t y ) {
	int32_t ox = (x >> 12) << 12, oy = (y >> 12) << 12;
	int n = 0;
	for( int i = 0; i < Nf; i++ ) {
		const seg_t* s = &Fsegs[i];
		int32_t x0 = Fx[i], x1 = Fx[i]+s->dx, y0 = Fy[i], y1 = Fy[i]+s->dy;
		if( x0 > x1 ) { int32_t t = x0; x0 = x1; x1 = t; }
		if( y0 > y1 ) { int32_t t = y0; y0 = y1; y1 = t; }
		if( x1 < ox-512 || x0 > ox+4096+512 || y1 < oy-512 || y0 > oy+4096+512 )
			continue;
		Cell[n] = *s;
		Cell[n].px = (int16_t)(Fx[i]-ox);
		Cell[n].py = (int16_t)(Fy[i]-oy);
		n++;
	}
	if( n > 255 )
		n = 255;
	Seg_cur = Cell;
	Seg_left = (uint8_t)n;
	Seg_ox = ox;
	Seg_oy = oy;
}

const seg_t* seg_next( void ) {
	if( !Seg_left )
		return NULL;
	Seg_left--;
	return Seg_cur++;
}

static void addfseg( double x, double y, double dx, double dy ) {
	double l = sqrt( dx*dx + dy*dy );
	if( l < 1e-6 )
		return;
	int parts = (int)(l/8.0) + 1;
	for( int i = 0; i < parts; i++ ) {
		double x0 = x + dx*i/parts, y0 = y + dy*i/parts;
		double x1 = x + dx*(i+1)/parts, y1 = y + dy*(i+1)/parts;
		int32_t px = (int32_t)lround( x0*1024 ), py = (int32_t)lround( y0*1024 );
		int32_t qx = (int32_t)lround( x1*1024 ), qy = (int32_t)lround( y1*1024 );
		double ddx = qx-px, ddy = qy-py, ll = sqrt( ddx*ddx + ddy*ddy );
		if( ll < 0.5 )
			continue;
		Fx[Nf] = px;
		Fy[Nf] = py;
		seg_t* s = &Fsegs[Nf++];
		s->dx = (int16_t)(qx-px);
		s->dy = (int16_t)(qy-py);
		s->ex = (int16_t)lround( ddx/ll*16384 );
		s->ey = (int16_t)lround( ddy/ll*16384 );
		s->len = (int16_t)lround( ll );
	}
}

static void tofix( const rbike* r ) {
	const rcircle* rc[3] = { &r->body, &r->wheel[0], &r->wheel[1] };
	circle_t* fc[3] = { &Bike.body, &Bike.wheel[0], &Bike.wheel[1] };
	for( int i = 0; i < 3; i++ ) {
		fc[i]->rx = lround( rc[i]->r.x*PH_S );
		fc[i]->ry = lround( rc[i]->r.y*PH_S );
		fc[i]->vx = (int16_t)lround( rc[i]->v.x*PH_VS );
		fc[i]->vy = (int16_t)lround( rc[i]->v.y*PH_VS );
		fc[i]->alfa = (uint32_t)(int64_t)llround( rc[i]->alfa*PH_AN );
		fc[i]->omega = (int16_t)lround( rc[i]->omega*PH_WS );
	}
	Bike.rider_x = lround( r->rider_r.x*PH_S );
	Bike.rider_y = lround( r->rider_r.y*PH_S );
	Bike.rider_vx = (int16_t)lround( r->rider_v.x*PH_VS );
	Bike.rider_vy = (int16_t)lround( r->rider_v.y*PH_VS );
	Bike.turned = (uint8_t)r->turned;
}

static void compare( rbike* rb, double now, int in ) {
	rbike r0 = *rb;
	tofix( rb );
	bike_t f0 = Bike;
	ref_step( rb, Rsegs, Nr, now, PH_H, in & IN_GAS, in & IN_BRAKE, in & IN_VOLT_RIGHT, in & IN_VOLT_LEFT );
	ph_step( (uint8_t)in );
	const rcircle* rc0[3] = { &r0.body, &r0.wheel[0], &r0.wheel[1] };
	const rcircle* rc1[3] = { &rb->body, &rb->wheel[0], &rb->wheel[1] };
	const circle_t* fc0[3] = { &f0.body, &f0.wheel[0], &f0.wheel[1] };
	const circle_t* fc1[3] = { &Bike.body, &Bike.wheel[0], &Bike.wheel[1] };
	const char* nm[3] = { "body", "w0", "w1" };
	for( int i = 0; i < 3; i++ )
		printf( "%-4s dv ref %9.5f %9.5f fix %9.5f %9.5f | dw ref %9.4f fix %9.4f\n", nm[i],
			rc1[i]->v.x-rc0[i]->v.x, rc1[i]->v.y-rc0[i]->v.y,
			(fc1[i]->vx-fc0[i]->vx)/PH_VS, (fc1[i]->vy-fc0[i]->vy)/PH_VS,
			rc1[i]->omega-rc0[i]->omega, (fc1[i]->omega-fc0[i]->omega)/PH_WS );
}

int main( int argc, char** argv ) {
	if( argc < 3 ) {
		fprintf( stderr, "usage: physcmp LEVEL.txt INPUTS\n" );
		return 1;
	}
	FILE* f = fopen( argv[1], "r" );
	double sx, sy;
	if( !f || fscanf( f, "%d %lf %lf", &Nr, &sx, &sy ) != 3 )
		return 1;
	for( int i = 0; i < Nr; i++ ) {
		rseg* s = &Rsegs[i];
		if( fscanf( f, "%lf %lf %lf %lf", &s->r.x, &s->r.y, &s->v.x, &s->v.y ) != 4 )
			return 1;
		addfseg( s->r.x, s->r.y, s->v.x, s->v.y );
	}
	fclose( f );

	rbike rb;
	ref_init( &rb, sx, sy );
	ph_init( (int32_t)lround( sx*PH_S ), (int32_t)lround( sy*PH_S ) );
	double dt = PH_H, now = 0;
	int step = 0, rdead = 0, fdead = 0;
	int lastvolt = -1000;
	const char* p = argv[2];
	int verbose = argc > 3;
	int sub = getenv( "REFSUB" ) ? atoi( getenv( "REFSUB" ) ) : 1;
	int onestep = getenv( "ONESTEP" ) ? atoi( getenv( "ONESTEP" ) ) : -1;
	while( *p ) {
		while( *p == ' ' ) p++;
		int in = 0, turn = 0;
		while( *p && strchr( "GBRLTN", *p ) ) {
			switch( *p ) {
				case 'G': in |= IN_GAS; break;
				case 'B': in |= IN_BRAKE; break;
				case 'R': in |= IN_VOLT_RIGHT; break;
				case 'L': in |= IN_VOLT_LEFT; break;
				case 'T': turn = 1; break;
			}
			p++;
		}
		int n = (int)strtol( p, (char**)&p, 10 );
		if( turn ) {
			rb.turned = !rb.turned;
			ph_turn();
		}
		for( int i = 0; i < n; i++, step++ ) {
			int fin = in;
			// A volt is pressed once, and only 0.4 s after the last one:
			if( fin & (IN_VOLT_LEFT | IN_VOLT_RIGHT) ) {
				if( i > 0 || step-lastvolt < (int)(0.4/PH_H) )
					fin &= ~(IN_VOLT_LEFT | IN_VOLT_RIGHT);
				else
					lastvolt = step;
			}
			if( step == onestep ) {
				rbike r2 = rb;
				bike_t f2 = Bike;
				compare( &r2, now, fin );
				Bike = f2;
			}
			// The reference may take substeps (the game steps 0.003 s):
			for( int j = 0; j < sub && !rdead; j++ ) {
				int v = j == 0 ? fin : 0;
				if( !ref_step( &rb, Rsegs, Nr, now+dt*j/sub, dt/sub, fin & IN_GAS,
						fin & IN_BRAKE, v & IN_VOLT_RIGHT, v & IN_VOLT_LEFT ) ) {
					rdead = step;
					printf( "ref died at step %d\n", step );
				}
			}
			if( !fdead && !ph_step( (uint8_t)fin ) ) {
				fdead = step;
				printf( "fix died at step %d\n", step );
			}
			now += dt;
			if( verbose || step % 30 == 0 ) {
				double fx = Bike.body.rx/PH_S, fy = Bike.body.ry/PH_S;
				double fa = (Bike.body.alfa & 0xffffff)/16777216.0*360.0;
				double ra = fmod( rb.body.alfa*180/M_PI + 3600, 360 );
				printf( "%5d ref body %8.3f %8.3f a %6.1f w %7.3f %7.3f | fix %8.3f %8.3f a %6.1f w %7.3f %7.3f | d %.3f\n",
						step, rb.body.r.x, rb.body.r.y, ra,
						rb.wheel[0].r.y, rb.wheel[1].r.y,
						fx, fy, fa, Bike.wheel[0].ry/PH_S, Bike.wheel[1].ry/PH_S,
						hypot( fx-rb.body.r.x, fy-rb.body.r.y ) );
			}
		}
	}
	return 0;
}
