
""" Module for laying out text in a grid pattern. Should not depend on anything but string manipulation """

class GridFormatter:
    def __init__(self, grid, numColumns, maxWidth=None):
        self.grid = grid
        self.numColumns = numColumns
        self.maxWidth = maxWidth

    def __str__(self):
        colWidths = self.findColumnWidths()
        totalWidth = sum(colWidths)
        if self.maxWidth is not None and totalWidth > self.maxWidth: # After a while, excessively wide grids just get too hard to read
            header = "." * 6 + " " + str(self.numColumns) + "-Column Layout " + "." * 6
            desc = self.formatColumnsInGrid()
            footer = "." * len(header)
            return header + "\n" + desc + "\n" + footer
        else:
            return self.formatCellsInGrid(colWidths)

    def isHorizontalRow(self):
        return len(self.grid) == 1 and self.numColumns > 1

    def findColumnWidths(self):
        colWidths = []
        for colNum in range(self.numColumns):
            maxWidth = max((self.getCellWidth(row, colNum) for row in self.grid))
            if colNum == self.numColumns - 1:
                colWidths.append(maxWidth)
            else:
                # Pad two spaces between each column
                colWidths.append(maxWidth + 2)
        return colWidths

    def getCellWidth(self, row, colNum):
        # Don't include rows which span several columns
        if len(row) == self.numColumns:
            lines = row[colNum].splitlines()
            if lines:
                return max((len(line) for line in lines))
        return 0

    def formatColumnsInGrid(self):
        desc = ""
        for colNum in range(self.numColumns):
            for row in self.grid:
                if colNum < len(row):
                    desc += row[colNum] + "\n"
            desc += "\n"
        return desc.rstrip()

    def formatCellsInGrid(self, colWidths):
        lines = []
        for row in self.grid:
            rowLines = max((desc.count("\n") + 1 for desc in row))
            for rowLine in range(rowLines):
                lineText = ""
                for colNum, childDesc in enumerate(row):
                    cellLines = childDesc.splitlines()
                    if rowLine < len(cellLines):
                        cellRow = cellLines[rowLine]
                    else:
                        cellRow = ""
                    lineText += cellRow.ljust(colWidths[colNum])
                lines.append(lineText.rstrip(" ")) # don't leave trailing spaces        
        return "\n".join(lines)
