`timescale 1ns / 1ps

module pwm_generator #(
    parameter integer WIDTH = 8
) (
    input wire clk,
    input wire [WIDTH-1:0] duty,
    output reg pwm_out
);

    reg [WIDTH-1:0] counter = {WIDTH{1'b0}};

    always @(posedge clk) begin
        counter <= counter + 1'b1;
        pwm_out <= counter < duty;
    end

endmodule
