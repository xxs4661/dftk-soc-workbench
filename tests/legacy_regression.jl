# Execute the old classifier expression with an unrelated injected exception message.
# This is a control-flow regression, not a pseudopotential or physical calculation.
using Test
source = read(only(ARGS), String)
line = only(filter(l -> occursin("status = occursin(\"unsupported\"", l), split(source, '\n')))
expression = Meta.parse(strip(split(line, "="; limit=2)[2]))
message = "unrelated unsupported feature"
old_status = Core.eval(@__MODULE__, expression)
println("Old classification of unrelated exception: ", old_status)
@test old_status != "REJECTED"
