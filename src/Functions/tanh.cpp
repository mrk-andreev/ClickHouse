#include <Functions/FunctionMathUnary.h>
#include <Functions/FunctionFactory.h>

namespace DB
{

namespace ErrorCodes
{
extern const int NOT_IMPLEMENTED;
}

namespace
{

struct TanhName { static constexpr auto name = "tanh"; };

#if USE_FASTOPS

    struct Impl
    {
        static constexpr auto name = TanhName::name;
        static constexpr auto rows_per_iteration = 0;
        static constexpr bool always_returns_float64 = false;

        template <typename T>
        static void execute(const T * src, size_t size, T * dst)
        {
            if constexpr (std::is_same_v<T, BFloat16>)
            {
                throw Exception(ErrorCodes::NOT_IMPLEMENTED, "Function `{}` is not implemented for BFloat16", name);
            }
            else
            {
                NFastOps::Tanh<>(src, size, dst);
            }
        }
    };

using FunctionTanh = FunctionMathUnary<Impl>;

#else

double tanh(double x)
{
    return 2 / (1.0 + exp(-2 * x)) - 1;
}

using FunctionTanh = FunctionMathUnary<UnaryFunctionVectorized<TanhName, tanh>>;
#endif

}

REGISTER_FUNCTION(Tanh)
{
    factory.registerFunction<FunctionTanh>({}, FunctionFactory::Case::Insensitive);
}

}
