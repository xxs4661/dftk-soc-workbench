# Synthetic observer protocol tests. No UPF, material context, FFT, eigen/FD
# solve, SCF or production slot is run; actual validation definitions are used.
include("soc_boundary/fixtures.jl")
include("../benchmarks/soc-validation-local-v1/observe.jl")
using .ValidationLocalObserver

struct ObserverCopyCounter <: AbstractVector{Float64}
    values::Vector{Float64}
    copies::Base.RefValue{Int}
    failure
end
Base.size(a::ObserverCopyCounter)=size(a.values)
Base.getindex(a::ObserverCopyCounter,i::Int)=a.values[i]
Base.strides(::ObserverCopyCounter)=error("Unknown metadata method must not run")
function Base.copy(a::ObserverCopyCounter)
    a.copies[]+=1
    isnothing(a.failure) || throw(a.failure)
    copy(a.values)
end

function observed_call(f,o,name)
    start_trace!(o,name)
    value=Base.invokelatest(f)
    value,finish_trace!(o)
end
function direct_storage(mod,rt,cert,sequence,role)
    role=="S" && return mod._check_storage(cert,sequence)
    mod._with_validation(rt) do memo
        mod._check_storage(cert,sequence,memo)
    end
end

@testset "Diagnostic shadow preserves source/hash and does not enter main timing" begin
    mktempdir() do reference_root
        target=joinpath(reference_root,"prototypes/fr_integration");mkpath(target)
        for file in ("common_data.jl","hamiltonian.jl","runtime.jl")
            relative="prototypes/fr_integration/"*file
            write(joinpath(target,file),read(`git -C $BOUNDARY_ROOT show $(BOUNDARY_REFERENCE*":"*relative)`))
        end
        for (role,mod,root,policy) in (("S",BoundaryReference,reference_root,:strict),
                                     ("F",BoundaryCandidate,BOUNDARY_ROOT,:single_validation_v1))
            f=synthetic_runtime(mod;policy)
            values=[0.0,-0.0,2.,3.];viewed=@view values[1:2:4]
            sequence=[("1/repeated_first",values),("1/fallback",viewed),("1/repeated_after",values),
                      ("1/fallback_again",viewed)]
            certificate=mod._storage_certificate(sequence)
            original_digests=[mod._fr_array_hash(a) for (_,a) in sequence]
            source_before=mod._source_snapshot(f.ctx.bundles[1].common)
            counters_before=role=="F" ? copy(f.rt._validation_counters) : nothing
            @test mod.runtime_boundary!(f.rt,:unobserved_before;ham=f.full)
            counters_after=role=="F" ? copy(f.rt._validation_counters) : nothing
            obs=install_observer!(mod,role,root)
            try
                @test !obs.enabled
                @test !isempty(observer_manifest(obs)["patches"])
                @test_throws ErrorException install_observer!(mod,role,root)
                value,trace=observed_call(obs,"boundary") do
                    mod.runtime_boundary!(f.rt,:observed;ham=f.full)
                end
                @test value===true
                @test trace["scope"]=="INSTRUMENTED_DIAGNOSTIC_NOT_MAIN_TIMING"
                @test trace["source_hash_calls"]==(role=="S" ? 6 : 3)
                if role=="F"
                    for key in keys(counters_before)
                        startswith(key,"max_live") && continue
                        @test f.rt._validation_counters[key]-counters_after[key] == counters_after[key]-counters_before[key]
                    end
                end
                @test trace["source_hash_bytes"]>0
                @test all(e["digest"]==source_before for e in trace["events"] if e["kind"]=="source_snapshot" && e["label"]=="common")
                @test Set(e["section"] for e in trace["events"] if e["kind"]=="array")==Set(["P/D","derived_storage","current_storage"])
                @test trace["observer_live_object_entries_after_finish"]==0
                @test isempty(obs.objects) && isempty(obs.hashed)
                @test !isempty(trace["methods"])
                @test all(!occursin(root,v["file"]) for v in Base.values(trace["methods"]))
                value,trace=observed_call(obs,"storage_sequence") do
                    direct_storage(mod,f.rt,certificate,sequence,role)
                end
                @test value===true
                arrays=filter(e->e["kind"]=="array",trace["events"])
                @test length(arrays)==4
                @test getindex.(arrays,"digest")==original_digests
                @test arrays[1]["object_id"]==arrays[3]["object_id"]
                @test arrays[2]["parent_id"]==arrays[1]["object_id"]
                @test trace["array_hash_calls"]==(role=="S" ? 2 : 4)
                @test trace["array_reuses"]==(role=="S" ? 2 : 0)
                @test arrays[3]["prior_hashes_same_key"]==1
                @test trace["memo_invalidations"]==(role=="S" ? 0 : 2)
                @test trace["memo_clear_operations"]==(role=="S" ? 0 : 4)
                if role=="F"
                    kinds=[e["kind"] for e in trace["events"]]
                    @test kinds==["array","memo_invalidation","array","memo_invalidation",
                                  "array","memo_invalidation","array","memo_invalidation"]
                    @test arrays[3]["branch"]=="canonical_hash"
                    @test arrays[2]["branch"]=="fallback"
                    @test isnothing(f.rt._validation_active)
                else
                    @test arrays[3]["branch"]=="reuse"
                end
                copies=Ref(0);custom=ObserverCopyCounter([1.,2.],copies,nothing)
                expected=bytes2hex(sha256(reinterpret(UInt8,copy(custom.values))))
                value,trace=observed_call(obs,"custom_copy") do
                    mod._fr_array_hash(custom)
                end
                @test copies[]==1 && value==expected
                @test only(trace["events"])["strides"]===nothing
                failure=ErrorException("original synthetic copy failure")
                broken=ObserverCopyCounter([1.],Ref(0),failure)
                start_trace!(obs,"throwing_copy")
                @test captured(()->Base.invokelatest(mod._fr_array_hash,broken))===failure
                @test clear_observer!(obs)["live_object_entries"]==0
                @test broken.copies[]==1
                if role=="F"
                    start_trace!(obs,"throwing_fallback")
                    @test captured(()->Base.invokelatest(()->mod._with_validation(f.rt) do memo
                        mod._validation_array_hash(memo,broken)
                    end))===failure
                    @test isnothing(f.rt._validation_active)
                    partial=finish_trace!(obs)
                    @test partial["array_hash_calls"]==0
                    @test partial["memo_clear_operations"]==2
                    @test partial["observer_live_object_entries_after_finish"]==0
                end
                # Wrong identity must still fail before a cached hash can help.
                altered=copy(sequence);altered[3]=("1/repeated_after",copy(values))
                start_trace!(obs,"wrong_identity")
                @test captured(()->Base.invokelatest(direct_storage,mod,f.rt,certificate,altered,role)) isa ArgumentError
                clear_observer!(obs)
                @test Base.invokelatest(mod.runtime_boundary!,f.rt,:unobserved_after;ham=f.full)
                @test isempty(obs.events)
            finally
                clear_observer!(obs)
                Base.invokelatest(clean_fixture,f)
            end
            @test mod.runtime_summary(f.rt).closed
        end
    end
end
