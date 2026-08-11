`timescale 1ns / 1ps

module uart_tx #(
    parameter integer CLK_HZ = 100000000,
    parameter integer BAUD = 115200
) (
    input wire clk,
    input wire reset,
    input wire tx_start,
    input wire [7:0] tx_data,
    output reg tx_line,
    output reg busy,
    output reg done
);

    localparam integer CLKS_PER_BIT = CLK_HZ / BAUD;

    localparam [2:0] S_IDLE    = 3'd0;
    localparam [2:0] S_START   = 3'd1;
    localparam [2:0] S_DATA    = 3'd2;
    localparam [2:0] S_STOP    = 3'd3;
    localparam [2:0] S_CLEANUP = 3'd4;

    reg [2:0] state = S_IDLE;
    reg [31:0] clk_count = 32'd0;
    reg [2:0] bit_index = 3'd0;
    reg [7:0] data_latch = 8'd0;

    always @(posedge clk) begin
        if (reset) begin
            state <= S_IDLE;
            clk_count <= 32'd0;
            bit_index <= 3'd0;
            data_latch <= 8'd0;
            tx_line <= 1'b1;
            busy <= 1'b0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;

            case (state)
                S_IDLE: begin
                    tx_line <= 1'b1;
                    busy <= 1'b0;
                    clk_count <= 32'd0;
                    bit_index <= 3'd0;

                    if (tx_start) begin
                        data_latch <= tx_data;
                        busy <= 1'b1;
                        state <= S_START;
                    end
                end

                S_START: begin
                    tx_line <= 1'b0;
                    busy <= 1'b1;

                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= 32'd0;
                        state <= S_DATA;
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                S_DATA: begin
                    tx_line <= data_latch[bit_index];
                    busy <= 1'b1;

                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= 32'd0;

                        if (bit_index == 3'd7) begin
                            bit_index <= 3'd0;
                            state <= S_STOP;
                        end else begin
                            bit_index <= bit_index + 1;
                        end
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                S_STOP: begin
                    tx_line <= 1'b1;
                    busy <= 1'b1;

                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= 32'd0;
                        state <= S_CLEANUP;
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                S_CLEANUP: begin
                    tx_line <= 1'b1;
                    busy <= 1'b0;
                    done <= 1'b1;
                    state <= S_IDLE;
                end

                default: begin
                    state <= S_IDLE;
                end
            endcase
        end
    end

endmodule
