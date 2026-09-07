module WorkbenchEnvironment
using Pkg, TOML, SHA
export environment_identity, public_data, filehash

filehash(path) = bytes2hex(sha256(read(path)))
git(dir, args...) = strip(read(`git -C $dir $args`, String))

function public_data(value, root)
    if value isa AbstractString
        replace(value, root => "<workbench>", homedir() => "<home>")
    elseif value isa AbstractDict || value isa NamedTuple
        Dict(string(k) => public_data(v, root) for (k,v) in pairs(value))
    elseif value isa AbstractVector
        [public_data(v, root) for v in value]
    else
        value
    end
end

function environment_identity(root, modules)
    root = realpath(root)
    envdir = joinpath(root, "environment", "workbench")
    lockfile = joinpath(root, "config", "sources.lock")
    lock = TOML.parsefile(lockfile)
    expected = TOML.parsefile(joinpath(envdir, "checksums.toml"))
    reasons = String[]
    active = Base.active_project()
    active_manifest = Pkg.Types.Context().env.manifest_file
    project = joinpath(envdir, "Project.toml")
    manifest = joinpath(envdir, "Manifest.toml")
    samefile(a,b) = !isnothing(a) && isfile(a) && isfile(b) && realpath(a) == realpath(b)
    samefile(active, project) || push!(reasons, "Active project is not the workbench project")
    samefile(active_manifest, manifest) || push!(reasons, "Active Manifest is not the saved workbench Manifest")
    for (label, file) in (("project", project), ("manifest", manifest), ("source_lock", lockfile))
        filehash(file) == expected[label * "_sha256"] || push!(reasons, "$label checksum mismatch")
    end
    string(VERSION) == TOML.parsefile(manifest)["julia_version"] || push!(reasons, "Julia version mismatch")
    packages = Dict{String,Any}()
    for (key, mod) in zip(("dftk", "pseudopotentialio"), modules)
        spec = lock["source"][key]
        checkout = realpath(joinpath(root, spec["checkout"]))
        source_project = TOML.parsefile(joinpath(checkout, "Project.toml"))
        loaded_path = realpath(pathof(mod))
        loaded_checkout = realpath(git(dirname(loaded_path), "rev-parse", "--show-toplevel"))
        expected_path = realpath(joinpath(checkout, "src", source_project["name"] * ".jl"))
        commit = git(loaded_checkout, "rev-parse", "HEAD")
        dirty = git(loaded_checkout, "status", "--porcelain", "--untracked-files=all")
        uuid = string(Base.PkgId(mod).uuid)
        version = string(pkgversion(mod))
        loaded_path == expected_path && loaded_checkout == checkout || push!(reasons, "$key loaded from a different checkout")
        commit == spec["commit"] || push!(reasons, "$key loaded commit mismatch")
        isempty(dirty) || push!(reasons, "$key loaded checkout has local changes")
        uuid == source_project["uuid"] || push!(reasons, "$key loaded UUID mismatch")
        version == source_project["version"] || push!(reasons, "$key loaded version mismatch")
        packages[key] = (; path=loaded_path, checkout=loaded_checkout, uuid, version,
                          commit, expected_commit=spec["commit"], expected_path,
                          expected_uuid=source_project["uuid"], expected_version=source_project["version"],
                          worktree_status=isempty(dirty) ? "clean" : dirty)
    end
    (; status=isempty(reasons) ? "PASS" : "MISMATCH", reasons,
       active_project=active, active_manifest, julia_version=string(VERSION),
       project_sha256=filehash(project), manifest_sha256=filehash(manifest),
       source_lock_sha256=filehash(lockfile), packages)
end
end
