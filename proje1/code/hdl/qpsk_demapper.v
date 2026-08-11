`timescale 1ns / 1ps

module qpsk_demapper (
    input wire i_positive,
    input wire q_positive,
    output wire [1:0] bit_pair
);

    // Reverse of qpsk_mapper.v.
    assign bit_pair[1] = ~q_positive;
    assign bit_pair[0] = ~i_positive;

endmodule
