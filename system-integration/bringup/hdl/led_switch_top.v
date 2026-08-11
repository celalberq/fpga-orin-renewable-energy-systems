`timescale 1ns / 1ps

module led_switch_top (
    input wire clk,
    input wire cpu_resetn,
    input wire [7:0] sw,
    output wire [7:0] led
);

    wire reset = ~cpu_resetn;

    assign led = reset ? 8'h00 : sw;

    wire unused_clk = clk;

endmodule
