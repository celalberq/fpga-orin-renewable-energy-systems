`timescale 1ns / 1ps

module crc8_byte (
    input wire [7:0] crc_in,
    input wire [7:0] data_in,
    output reg [7:0] crc_out
);

    integer bit_index;
    reg [7:0] crc_work;

    always @* begin
        crc_work = crc_in ^ data_in;

        for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
            if (crc_work[7]) begin
                crc_work = (crc_work << 1) ^ 8'h07;
            end else begin
                crc_work = crc_work << 1;
            end
        end

        crc_out = crc_work;
    end

endmodule
