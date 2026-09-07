module UpfRuntime
using PseudoPotentialIO
export parse_input, metadata_from_upf

function parse_input(path; loader=PseudoPotentialIO.load_psp_file)
    try
        parsed = loader(path)
        parsed isa PseudoPotentialIO.UpfFile || return (
            status="FAIL", parsed=nothing, reasons=["Input did not parse as UpfFile"])
        (; status="PASS", parsed, reasons=String[])
    catch err
        (; status="FAIL", parsed=nothing, reasons=[sprint(showerror, err)])
    end
end

function metadata_from_upf(parsed)
    (; is_upf=true, pseudo_type=parsed.header.pseudo_type, has_so=parsed.header.has_so,
       relativistic=parsed.header.relativistic, declared_count=parsed.header.number_of_proj,
       betas=[(; index=b.index, l=b.angular_momentum) for b in parsed.nonlocal.betas],
       relbetas=isnothing(parsed.spin_orb) ? nothing :
           [(; index=b.index, l=b.lll, j=b.jjj) for b in parsed.spin_orb.relbetas])
end
end
