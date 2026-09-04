#!/usr/bin/env julia

using DFTK
using PseudoPotentialIO
using SHA
using TOML

const WORKBENCH_ROOT = normpath(joinpath(@__DIR__, ".."))
const SOURCES_LOCK = joinpath(WORKBENCH_ROOT, "config", "sources.lock")

function usage(io::IO=stdout)
    println(io, "Usage: inspect_relativistic_upf.jl [options] UPF_PATH")
    println(io)
    println(io, "Parse one UPF without dumping radial arrays, then separately attempt")
    println(io, "construction through DFTK.PspUpf.")
    println(io)
    println(io, "Options:")
    println(io, "  --json PATH              Write deterministic JSON to PATH")
    println(io, "  --display-path PATH      Sanitized input path stored in JSON")
    println(io, "  --family-id ID           Pseudopotential family identifier")
    println(io, "  --source-id ID           Source or package identifier")
    println(io, "  --redistribution STATUS  Observed redistribution status")
    println(io, "  -h, --help               Show this help")
end

function parse_arguments(args)
    options = Dict{String,Union{Nothing,String}}(
        "json" => nothing,
        "display-path" => nothing,
        "family-id" => nothing,
        "source-id" => nothing,
        "redistribution" => nothing,
    )
    positional = String[]
    i = 1
    while i <= length(args)
        arg = args[i]
        if arg in ("-h", "--help")
            return (; help=true, options, positional)
        elseif startswith(arg, "--")
            key = arg[3:end]
            haskey(options, key) || error("Unknown option: $arg")
            i == length(args) && error("Option $arg requires a value")
            options[key] = args[i + 1]
            i += 2
        else
            push!(positional, arg)
            i += 1
        end
    end
    (; help=false, options, positional)
end

function sanitized_message(err, input_path)
    message = sprint(showerror, err)
    message = replace(message, abspath(input_path) => "<upf-input>")
    replace(message, homedir() => "<home>")
end

function sha256_file(path)
    open(path, "r") do io
        bytes2hex(sha256(io))
    end
end

function write_json_string(io, value::AbstractString)
    print(io, '"')
    for character in value
        if character == '"'
            print(io, "\\\"")
        elseif character == '\\'
            print(io, "\\\\")
        elseif character == '\b'
            print(io, "\\b")
        elseif character == '\f'
            print(io, "\\f")
        elseif character == '\n'
            print(io, "\\n")
        elseif character == '\r'
            print(io, "\\r")
        elseif character == '\t'
            print(io, "\\t")
        elseif Int(character) < 0x20
            print(io, "\\u", lpad(string(Int(character); base=16), 4, '0'))
        else
            print(io, character)
        end
    end
    print(io, '"')
end

function write_json(io, value; indentation=0)
    if isnothing(value)
        print(io, "null")
    elseif value isa Bool
        print(io, value ? "true" : "false")
    elseif value isa Number
        isfinite(value) || error("Cannot serialize a non-finite number as JSON")
        print(io, value)
    elseif value isa AbstractString
        write_json_string(io, value)
    elseif value isa NamedTuple
        names = propertynames(value)
        isempty(names) && return print(io, "{}")
        println(io, "{")
        for (position, name) in enumerate(names)
            print(io, " "^(indentation + 2))
            write_json_string(io, string(name))
            print(io, ": ")
            write_json(io, getproperty(value, name); indentation=indentation + 2)
            position == length(names) ? println(io) : println(io, ',')
        end
        print(io, " "^indentation, '}')
    elseif value isa AbstractVector
        isempty(value) && return print(io, "[]")
        println(io, "[")
        for (position, item) in enumerate(value)
            print(io, " "^(indentation + 2))
            write_json(io, item; indentation=indentation + 2)
            position == length(value) ? println(io) : println(io, ',')
        end
        print(io, " "^indentation, ']')
    else
        error("Unsupported JSON value type: $(typeof(value))")
    end
end

function write_result(output_path, result)
    if isnothing(output_path)
        write_json(stdout, result)
        println()
    else
        open(output_path, "w") do io
            write_json(io, result)
            println(io)
        end
    end
end

function source_revisions()
    lock = TOML.parsefile(SOURCES_LOCK)
    (; dftk=lock["source"]["dftk"]["commit"],
       pseudopotentialio=lock["source"]["pseudopotentialio"]["commit"])
end

function loaded_versions()
    manifest = TOML.parsefile(joinpath(WORKBENCH_ROOT, ".work", "DFTK.jl", "Manifest.toml"))
    ppio = only(manifest["deps"]["PseudoPotentialIO"])
    (; dftk=string(pkgversion(DFTK)),
       pseudopotentialio=string(pkgversion(PseudoPotentialIO)),
       pseudopotentialio_tree_sha1=ppio["git-tree-sha1"])
end

function inspect_upf(input_path, display_path, provenance)
    checksum = sha256_file(input_path)
    parsed = try
        PseudoPotentialIO.load_psp_file(input_path)
    catch err
        result = (
            schema_version=1,
            status="FAIL",
            source_revisions=source_revisions(),
            input=(; path=display_path, file_name=basename(input_path), sha256=checksum,
                   provenance...),
            raw_upf_parsing=(; status="FAIL", parser="PseudoPotentialIO.load_psp_file",
                             error_type=string(typeof(err)),
                             error_message=sanitized_message(err, input_path)),
            dftk_construction=(; attempted=false, status="NOT RUN"),
        )
        return result, 3
    end

    if !(parsed isa PseudoPotentialIO.UpfFile)
        result = (
            schema_version=1,
            status="FAIL",
            source_revisions=source_revisions(),
            input=(; path=display_path, file_name=basename(input_path), sha256=checksum,
                   provenance...),
            raw_upf_parsing=(; status="FAIL", parser="PseudoPotentialIO.load_psp_file",
                             error_type="UnexpectedParsedType",
                             error_message="Input did not parse as PseudoPotentialIO.UpfFile"),
            dftk_construction=(; attempted=false, status="NOT RUN"),
        )
        return result, 4
    end

    betas = parsed.nonlocal.betas
    spin_orb = parsed.spin_orb
    relbetas = isnothing(spin_orb) ? PseudoPotentialIO.UpfRelBeta[] : spin_orb.relbetas
    relwfcs = isnothing(spin_orb) ? PseudoPotentialIO.UpfRelWfc[] : spin_orb.relwfcs

    beta_records = [(; position=i, index=beta.index, l=beta.angular_momentum)
                    for (i, beta) in enumerate(betas)]
    relativistic_beta_records = map(relbetas) do relbeta
        index = relbeta.index
        matches_beta = !isnothing(index) && 1 <= index <= length(betas) &&
                       betas[index].index == index
        (; index, l=relbeta.lll, j=relbeta.jjj, matches_beta_index=matches_beta)
    end
    relativistic_wavefunction_records = [
        (; index=wfc.index, l=wfc.lchi, j=wfc.jchi, principal_n=wfc.nn)
        for wfc in relwfcs
    ]

    construction = try
        DFTK.PspUpf(parsed; identifier=basename(input_path))
        (; attempted=true, status="CONSTRUCTED", error_type=nothing, error_message=nothing)
    catch err
        message = sanitized_message(err, input_path)
        status = occursin("unsupported", lowercase(message)) ? "REJECTED" : "ERROR"
        (; attempted=true, status, error_type=string(typeof(err)), error_message=message)
    end

    result = (
        schema_version=1,
        status=construction.status == "ERROR" ? "FAIL" : "PASS",
        source_revisions=source_revisions(),
        loaded_packages=loaded_versions(),
        input=(; path=display_path, file_name=basename(input_path), sha256=checksum,
               provenance...),
        raw_upf_parsing=(; status="PASS", parser="PseudoPotentialIO.load_psp_file",
                         parsed_type=string(typeof(parsed))),
        upf=(;
            version=parsed.version,
            pseudo_type=parsed.header.pseudo_type,
            relativistic=parsed.header.relativistic,
            has_so=parsed.header.has_so,
            element=parsed.header.element,
            beta_projector_count=length(betas),
            beta_angular_momenta=[beta.angular_momentum for beta in betas],
            beta_records,
            relativistic_beta_record_count=length(relbetas),
            relativistic_beta_l_values=sort(unique([beta.lll for beta in relbetas
                                                    if !isnothing(beta.lll)])),
            relativistic_beta_j_values=sort(unique([beta.jjj for beta in relbetas])),
            relativistic_beta_records,
            relativistic_wavefunction_records_present=!isempty(relwfcs),
            relativistic_wavefunction_record_count=length(relwfcs),
            relativistic_wavefunction_records,
        ),
        dftk_construction=construction,
    )
    result, construction.status == "ERROR" ? 5 : 0
end

function main(args)
    parsed_args = try
        parse_arguments(args)
    catch err
        println(stderr, "Argument error: ", sprint(showerror, err))
        usage(stderr)
        return 2
    end
    if parsed_args.help
        usage()
        return 0
    end
    if length(parsed_args.positional) != 1
        println(stderr, "Expected exactly one UPF path.")
        usage(stderr)
        return 2
    end

    input_path = only(parsed_args.positional)
    output_path = parsed_args.options["json"]
    display_path = something(parsed_args.options["display-path"], input_path)
    if !isfile(input_path)
        println(stderr, "Input does not exist or is not a file: ", display_path)
        return 2
    end

    provenance = (;
        family_identifier=parsed_args.options["family-id"],
        source_identifier=parsed_args.options["source-id"],
        redistribution_status=parsed_args.options["redistribution"],
    )
    result, exit_code = inspect_upf(input_path, display_path, provenance)
    write_result(output_path, result)

    println("Raw UPF parsing: ", result.raw_upf_parsing.status)
    println("DFTK construction: ", result.dftk_construction.status)
    println("Inspection status: ", result.status)
    !isnothing(output_path) && println("JSON output: results/upf-inspection.json")
    exit_code
end

exit(main(ARGS))
