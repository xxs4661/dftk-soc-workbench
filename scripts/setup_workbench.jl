using Pkg, TOML, SHA

const ROOT = realpath(joinpath(@__DIR__, ".."))
const ENV_DIR = joinpath(ROOT, "environment", "workbench")
lock = TOML.parsefile(joinpath(ROOT, "config", "sources.lock"))
hashfile(p) = bytes2hex(sha256(read(p)))
git(dir, args...) = strip(read(`git -C $dir $args`, String))

function sources(action, cache)
    for key in ("dftk", "pseudopotentialio")
        spec = lock["source"][key]
        target = joinpath(ROOT, spec["checkout"])
        if !isdir(target)
            action == "fetch" || error("Missing source checkout: $(spec["checkout"])")
            mkpath(dirname(target))
            origin = isnothing(cache) ? spec["repository"] : joinpath(cache, basename(target))
            run(`git clone --quiet --no-hardlinks --no-checkout $origin $target`)
            run(`git -C $target remote set-url origin $(spec["repository"])`)
            run(`git -C $target checkout --quiet --detach $(spec["commit"])`)
        end
        git(target, "rev-parse", "HEAD") == spec["commit"] || error("Wrong source commit: $key; existing checkout preserved")
        isempty(git(target, "status", "--porcelain", "--untracked-files=all")) ||
            error("Dirty source checkout: $key; existing changes preserved")
        println(stderr, "$key: ", spec["commit"], " clean")
    end
end

try
    action = isempty(ARGS) ? "" : ARGS[1]
    if action == "fetch"
        cache = length(ARGS) == 3 && ARGS[2] == "--source-cache" ? abspath(ARGS[3]) : nothing
        (length(ARGS) == 1 || !isnothing(cache)) || error("Usage: fetch [--source-cache DIR]")
        sources(action, cache)
    elseif action == "instantiate"
        length(ARGS) == 1 || error("instantiate takes no arguments")
        expected = TOML.parsefile(joinpath(ENV_DIR, "checksums.toml"))
        for (label, file) in (("project", joinpath(ENV_DIR, "Project.toml")),
                              ("manifest", joinpath(ENV_DIR, "Manifest.toml")),
                              ("source_lock", joinpath(ROOT, "config", "sources.lock")))
            hashfile(file) == expected[label * "_sha256"] || error("Saved $label checksum mismatch; refusing to instantiate")
        end
        sources(action, nothing)
        files = [joinpath(ENV_DIR, f) for f in ("Project.toml", "Manifest.toml")]
        before = hashfile.(files)
        manifest = TOML.parsefile(files[2])
        string(VERSION) == manifest["julia_version"] || error("Julia version differs from saved Manifest")
        Pkg.activate(ENV_DIR)
        Pkg.instantiate(; allow_autoprecomp=false)
        hashfile.(files) == before || error("Instantiation changed the saved environment; review required")
        sources(action, nothing)
        println(stderr, "Saved workbench environment instantiated without changing Project/Manifest")
    else
        error("Usage: setup_workbench.jl fetch [--source-cache DIR] | instantiate")
    end
catch err
    println(stderr, "BLOCKED: ", replace(sprint(showerror, err), ROOT => "<workbench>", homedir() => "<home>"))
    exit(7)
end
