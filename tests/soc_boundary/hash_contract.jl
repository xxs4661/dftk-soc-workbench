# Included by test_soc_boundary_protection.jl; same actual candidate runtime.
struct MutatingCopyArray <: AbstractVector{Float64}
    values::Vector{Float64}
    target::Vector{Float64}
end
Base.size(a::MutatingCopyArray)=size(a.values)
Base.getindex(a::MutatingCopyArray,i::Int)=a.values[i]
Base.copy(a::MutatingCopyArray)=(a.target[1]+=0.25;copy(a.values))
struct ThrowingCopyArray <: AbstractVector{Float64}
    original::Exception
end
Base.size(::ThrowingCopyArray)=(1,)
Base.getindex(::ThrowingCopyArray,i::Int)=1.0
Base.copy(a::ThrowingCopyArray)=throw(a.original)

@testset "Dense no-copy digest equals frozen byte convention; fallback never memoizes" begin
    f=synthetic_runtime(;policy=:single_validation_v1)
    try
        backing=reshape(collect(1.:12.),3,4)
        complex_backing=complex.(backing,reverse(backing;dims=1))
        cases=Any[Float64[],zeros(0,2),reshape([0.,-0.,1.5,-2.],2,2),
            ComplexF64[],reshape(ComplexF64[complex(0.,-0.),complex(-0.,0.),1+2im,-3-4im],2,2),
            reshape(collect(1.:8.),2,2,2),@view(backing[:,2:3]),@view(backing[1:2:3,1:2:4]),
            @view(complex_backing[:,2]),transpose(backing),adjoint(complex_backing),
            PermutedDimsArray(reshape(collect(1.:8.),2,2,2),(3,1,2)),Float32[1,2],Int16[-3,0,4]]
        for a in cases
            expected=bytes2hex(SHA.sha256(reinterpret(UInt8,vec(copy(a)))))
            @test BoundaryReference._fr_array_hash(a)==expected
            before=copy(FI.runtime_summary(f.rt).validation.counters)
            original=copy(a)
            FI._with_validation(f.rt) do memo
                @test FI._validation_array_hash(memo,a)==expected
                @test FI._validation_array_hash(memo,a)==expected
                if a isa Union{Array{Float64},Array{ComplexF64}}
                    @test length(memo.arrays)==1
                else
                    @test isempty(memo.arrays)
                end
            end
            after=FI.runtime_summary(f.rt).validation.counters
            canonical=a isa Union{Array{Float64},Array{ComplexF64}}
            @test after["array_hash_calls"]-before["array_hash_calls"]==(canonical ? 1 : 2)
            @test after["array_hash_reuses"]-before["array_hash_reuses"]==(canonical ? 1 : 0)
            @test after["fallback_hash_requests"]-before["fallback_hash_requests"]==(canonical ? 0 : 2)
            @test after["array_hash_bytes"]-before["array_hash_bytes"]==sizeof(copy(a))*(canonical ? 1 : 2)
            @test isequal(a,original)
            assert_no_live_memo(f.rt)
        end
        @test FI._fr_array_hash([0.])!=FI._fr_array_hash([-0.])
        @test FI._fr_array_hash(ComplexF64[complex(0.,0.)])!=FI._fr_array_hash(ComplexF64[complex(0.,-0.)])
        # Unknown copy methods are not assumed pure and cannot carry a cached
        # dense digest through their side effect or failure.
        target=[1.];custom=MutatingCopyArray([2.],target)
        FI._with_validation(f.rt) do memo
            old=FI._validation_array_hash(memo,target)
            @test FI._validation_array_hash(memo,custom)==FI._fr_array_hash([2.])
            @test isempty(memo.arrays)
            @test FI._validation_array_hash(memo,target)!=old
        end
        original=ErrorException("custom copy failed")
        err=captured(()->FI._with_validation(f.rt) do memo
            FI._validation_array_hash(memo,target)
            FI._validation_array_hash(memo,ThrowingCopyArray(original))
        end)
        @test err===original
        assert_no_live_memo(f.rt)
        # Forged token shares owner/generation but was never installed there.
        FI._with_validation(f.rt) do memo
            fake=FI._ValidationMemo(f.rt,memo.generation,memo.current,true,
                IdDict{Any,String}(),IdDict{Any,Nothing}(),memo.counters)
            @test_throws ArgumentError FI._validation_array_hash(fake,target)
            @test_throws ArgumentError FI._check_storage([(label="x",array=target,shape=(1,),sha256="fake")],[("x",target)],fake)
        end
    finally
        clean_fixture(f)
    end
end

@testset "Memo cannot relax per-occurrence storage identities or survive close" begin
    f=synthetic_runtime(;policy=:single_validation_v1)
    try
        array=[1.,2.];cert=FI._storage_certificate([("x",array)])
        FI._with_validation(f.rt) do memo
            @test FI._check_storage(cert,[("x",array)],memo)
            @test_throws ArgumentError FI._check_storage(cert,[("wrong-label",array)],memo)
            @test_throws ArgumentError FI._check_storage(cert,[("x",copy(array))],memo)
            @test_throws ArgumentError FI._check_storage(cert,[("x",array),("x",array)],memo)
            resize!(array,1)
            @test_throws ArgumentError FI._check_storage(cert,[("x",array)],memo)
        end
        saved=Ref{Any}(nothing)
        err=captured(()->FI._with_validation(f.rt) do memo
            saved[]=memo
            FI._validation_array_hash(memo,f.ctx.fr_blocks[1].P)
            FI.close_runtime!(f.rt) # nested generic boundary rejects, finally still releases
        end)
        @test err isa ArgumentError
        @test FI.runtime_summary(f.rt).closed && FI.runtime_summary(f.rt).workspace_released
        @test saved[].owner===nothing && saved[].current===nothing
        @test isempty(saved[].arrays) && isempty(saved[].sources)
        @test_throws ArgumentError FI._validation_array_hash(saved[],array)
        assert_no_live_memo(f.rt)
    finally
        clean_fixture(f)
    end
end
