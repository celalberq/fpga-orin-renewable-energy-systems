`timescale 1ns / 1ps

module qpsk_mapper (
    input wire [1:0] bit_pair,
    output wire i_positive,
    output wire q_positive
);

    // bit_pair[1] is the first bit in the pair, bit_pair[0] is the second bit.
    // 00 -> +I,+Q  01 -> -I,+Q  11 -> -I,-Q  10 -> +I,-Q
    assign i_positive = ~bit_pair[0];
    assign q_positive = ~bit_pair[1];

endmodule
