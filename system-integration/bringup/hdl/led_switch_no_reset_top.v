`timescale 1ns / 1ps

module led_switch_no_reset_top (
    input wire [7:0] sw,
    output wire [7:0] led
);

    assign led = sw;

endmodule
