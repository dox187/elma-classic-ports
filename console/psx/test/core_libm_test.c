/* Compares the vendored musl math subset (third_party/musl-libm) with the
 * host C library on the inputs that the game core gives these functions.
 * The desktop builds use the host library, so a difference here could make
 * a replay play differently on the PS1. Built by core_host_tests.sh, where
 * the musl files are compiled with an m_ prefix (m_sin, m_cos, ...). */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

double m_sin(double), m_cos(double), m_atan2(double, double), m_exp(double);
double m_sqrt(double), m_floor(double), m_ceil(double), m_fabs(double);

static uint64_t bits(double x) {
	uint64_t u;
	memcpy(&u, &x, sizeof u);
	return u;
}

/* Distance in units in the last place; 0 when both are the same NaN. */
static uint64_t ulps(double a, double b) {
	if (isnan(a) && isnan(b)) return 0;
	int64_t ia = (int64_t)bits(a), ib = (int64_t)bits(b);
	if (ia < 0) ia = INT64_MIN - ia;
	if (ib < 0) ib = INT64_MIN - ib;
	return ia > ib ? (uint64_t)(ia - ib) : (uint64_t)(ib - ia);
}

/* A small deterministic generator, so every run tests the same inputs. */
static uint64_t seed = 0x9e3779b97f4a7c15ull;
static double uniform(double lo, double hi) {
	seed ^= seed << 13;
	seed ^= seed >> 7;
	seed ^= seed << 17;
	return lo + (hi - lo) * ((seed >> 11) * (1.0 / 9007199254740992.0));
}

struct stats {
	const char* name;
	long count, differ;
	uint64_t worst;
	double worst_input;
};

static void check(struct stats* s, double input, double host, double musl) {
	uint64_t d = ulps(host, musl);
	s->count++;
	if (d) {
		s->differ++;
		if (d > s->worst) {
			s->worst = d;
			s->worst_input = input;
		}
	}
}

static int report(const struct stats* s, uint64_t allowed) {
	printf("%-6s %9ld inputs, %7ld differ (%.4f%%), worst %llu ulp", s->name, s->count,
	       s->differ, 100.0 * s->differ / (s->count ? s->count : 1),
	       (unsigned long long)s->worst);
	if (s->worst) printf(" at %.17g", s->worst_input);
	printf("\n");
	return s->worst <= allowed;
}

int main(void) {
	const long n = 2000000;
	struct stats ssin = {"sin"}, scos = {"cos"}, satan2 = {"atan2"}, sexp = {"exp"};
	struct stats ssqrt = {"sqrt"}, sfloor = {"floor"}, sceil = {"ceil"}, sfabs = {"fabs"};

	for (long i = 0; i < n; i++) {
		/* Wheel and body angles (kor1.alfa grows with every turn of the
		 * wheels), menu ball phases and small rotations: */
		double ranges[] = {6.3, 100.0, 1e4, 1e6};
		double a = uniform(-ranges[i % 4], ranges[i % 4]);
		check(&ssin, a, sin(a), m_sin(a));
		check(&scos, a, cos(a), m_cos(a));
		double small = uniform(-1e-3, 1e-3);
		check(&ssin, small, sin(small), m_sin(small));
		check(&scos, small, cos(small), m_cos(small));

		/* Polygon edge directions: */
		double scale = pow(10.0, uniform(-6, 4));
		double dx = uniform(-1, 1) * scale, dy = uniform(-1, 1) * scale;
		check(&satan2, dx, atan2(dy, dx), m_atan2(dy, dx));

		/* Engine sound frequency, 2 - exp(-f) with f >= 0: */
		double f = uniform(0, 30);
		check(&sexp, -f, exp(-f), m_exp(-f));

		/* Squared distances and lengths: */
		double q = pow(10.0, uniform(-12, 8)) * uniform(0, 1);
		check(&ssqrt, q, sqrt(q), m_sqrt(q));

		/* Zoom steps, coordinates: */
		double z = uniform(-1e5, 1e5);
		check(&sfloor, z, floor(z), m_floor(z));
		check(&sceil, z, ceil(z), m_ceil(z));
		check(&sfabs, z, fabs(z), m_fabs(z));
	}
	/* Exact and special values. */
	const double special[] = {0.0, -0.0, 1.0, -1.0, 0.5, -0.5, M_PI, -M_PI, M_PI / 2,
	                          M_PI / 4, 1e-300, 4.9e-324, 1e300, INFINITY, -INFINITY, NAN};
	for (unsigned i = 0; i < sizeof special / sizeof special[0]; i++) {
		double x = special[i];
		check(&ssin, x, sin(x), m_sin(x));
		check(&scos, x, cos(x), m_cos(x));
		check(&sexp, x, exp(x), m_exp(x));
		check(&ssqrt, x, sqrt(x), m_sqrt(x));
		check(&sfloor, x, floor(x), m_floor(x));
		check(&sceil, x, ceil(x), m_ceil(x));
		for (unsigned j = 0; j < sizeof special / sizeof special[0]; j++)
			check(&satan2, x, atan2(x, special[j]), m_atan2(x, special[j]));
	}

	/* sqrt, floor, ceil and fabs are exact in both libraries; the others
	 * may differ by one unit in the last place. */
	int ok = 1;
	ok &= report(&ssin, 1);
	ok &= report(&scos, 1);
	ok &= report(&satan2, 1);
	ok &= report(&sexp, 1);
	ok &= report(&ssqrt, 0);
	ok &= report(&sfloor, 0);
	ok &= report(&sceil, 0);
	ok &= report(&sfabs, 0);
	printf("%s\n", ok ? "PASS" : "FAIL");
	return ok ? 0 : 1;
}
